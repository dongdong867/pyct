import operator
import random
import re
import shutil
import subprocess
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Site
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import above, below, decode, encode

SITE = Site("m.py", 2, 7)

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

# a Python str, and the SMT-LIB literal it is written as: printable ASCII as itself, a double
# quote twice, and everything else, the backslash included, as its code point in hex
LITERALS: dict[str, tuple[str, str]] = {
    "empty": ("", '""'),
    "printable": ("abc XYZ 09 ~!", '"abc XYZ 09 ~!"'),
    "single-quote": ("it's", '"it\'s"'),
    "double-quote": ('say "hi"', '"say ""hi"""'),
    "backslash": ("a\\b", '"a\\u{5c}b"'),
    "tab": ("a\tb", '"a\\u{9}b"'),
    "newline": ("a\nb", '"a\\u{a}b"'),
    "nul": ("\x00", '"\\u{0}"'),
    "delete": ("\x7f", '"\\u{7f}"'),
    "past-ascii": ("é", '"\\u{e9}"'),
    "emoji": ("\U0001f600", '"\\u{1f600}"'),
    "last-character": ("\U0002ffff", '"\\u{2ffff}"'),
    "the-story's-literal": ('a\nb"c\\d é', '"a\\u{a}b""c\\u{5c}d \\u{e9}"'),
}


@pytest.mark.parametrize(("value", "literal"), LITERALS.values(), ids=list(LITERALS))
def test_a_str_is_written_as_the_literal_cvc5_reads(value: str, literal: str) -> None:
    assert encode(value) == literal


@pytest.mark.parametrize(("value", "literal"), LITERALS.values(), ids=list(LITERALS))
def test_a_literal_cvc5_prints_is_read_back_as_the_same_str(value: str, literal: str) -> None:
    assert decode(literal) == value


def test_a_character_past_the_last_one_cvc5_holds_is_refused() -> None:
    with pytest.raises(ValueError, match="U\\+30000"):
        encode("a\U00030000")


# what cvc5 never prints: a bare quote or backslash inside, an escape it does not write, a
# character it escapes, a code point past its last, and a value that is not quoted at all
UNREADABLE: dict[str, str] = {
    "lone-quote": '"a"b"',
    "lone-backslash": '"a\\b"',
    "four-digit-escape": '"\\u00e9"',
    "upper-case-hex": '"\\u{E9}"',
    "six-digit-escape": '"\\u{10000a}"',
    "past-the-last-character": '"\\u{30000}"',
    "raw-tab": '"a\tb"',
    "raw-past-ascii": '"é"',
    "unquoted": "abc",
    "one-quote": '"',
}


@pytest.mark.parametrize("literal", UNREADABLE.values(), ids=list(UNREADABLE))
def test_a_literal_cvc5_would_not_print_is_an_error(literal: str) -> None:
    with pytest.raises(ValueError, match="cvc5"):
        decode(literal)


@needs_cvc5
@pytest.mark.parametrize("value", [value for value, _ in LITERALS.values()], ids=list(LITERALS))
def test_the_real_cvc5_hands_back_the_str_it_was_given(value: str) -> None:
    equal = Branch(expression=["==", "s", repr(value)], taken=True, site=SITE)

    assert solve((equal,), {"s": str}, 10.0) == Sat({"s": value})


def test_an_order_against_a_literal_is_written_letter_by_letter() -> None:
    # the first letter that differs decides; past its end a string's letter is empty, whose
    # code is -1, below every character, so the one that runs out first is the smaller
    assert below("s", "ab", or_equal=False) == (
        "(or (< (str.to_code (str.at s 0)) 97)"
        ' (and (str.prefixof "a" s) (< (str.to_code (str.at s 1)) 98)))'
    )
    # the other way round, a string that has the whole literal and goes on is the larger
    assert above("s", "a", or_equal=True) == (
        '(or (= s "a") (> (str.to_code (str.at s 0)) 97)'
        ' (and (str.prefixof "a" s) (> (str.len s) 1)))'
    )


# an order against the empty literal, which has no letter to write: each is settled outright
EMPTY_LITERAL: dict[str, tuple[Callable[..., str], bool, str]] = {
    "s < ''": (below, False, "false"),
    "s <= ''": (below, True, '(= s "")'),
    "'' < s": (above, False, '(distinct s "")'),
    "'' <= s": (above, True, "true"),
}


@pytest.mark.parametrize(
    ("side", "or_equal", "written"), EMPTY_LITERAL.values(), ids=list(EMPTY_LITERAL)
)
def test_an_order_against_the_empty_literal_is_settled_outright(
    side: Callable[..., str], or_equal: bool, written: str
) -> None:
    assert side("s", "", or_equal=or_equal) == written


def test_the_tracked_side_is_written_as_the_term_it_is_given() -> None:
    term = "(str.substr s 1 2)"

    written = below(term, "x", or_equal=False)

    assert written == f"(< (str.to_code (str.at {term} 0)) 120)"


def test_a_literal_character_is_written_by_its_code_point() -> None:
    assert below("s", "\U0002ffff", or_equal=False) == "(< (str.to_code (str.at s 0)) 196607)"
    assert '(str.prefixof "\\u{e9}" s)' in above("s", "éa", or_equal=False)


# Python's own order on strings: what the letter-by-letter form must agree with
PYTHON_ORDERS: dict[str, tuple[Callable[..., str], bool, Callable[[str, str], bool]]] = {
    "<": (below, False, operator.lt),
    "<=": (below, True, operator.le),
    ">": (above, False, operator.gt),
    ">=": (above, True, operator.ge),
}

# the characters the random strings are made of: ASCII letters, the edges of what cvc5 holds,
# a letter past ASCII, a lone surrogate and an emoji
ALPHABET = ["a", "b", "z", "\x00", "\x7f", "é", "\ud800", "\U0001f600", "\U0002ffff"]


def _triples(count: int) -> list[tuple[str, str, str]]:
    """Random (value, op, literal) triples, fixed by the seed; half share a prefix."""
    rng = random.Random(0)
    triples = []
    for _ in range(count):
        literal = "".join(rng.choices(ALPHABET, k=rng.randint(0, 3)))
        value = "".join(rng.choices(ALPHABET, k=rng.randint(0, 3)))
        if rng.random() < 0.5:
            value = literal[: rng.randint(0, len(literal))] + value[: rng.randint(0, 1)]
        triples.append((value, rng.choice(list(PYTHON_ORDERS)), literal))
    return triples


def _truths(formulas: list[str]) -> list[bool]:
    """What cvc5 says each closed formula is, all in one call: one Bool constant apiece."""
    lines = ["(set-logic ALL)"]
    for at, formula in enumerate(formulas):
        lines += [f"(declare-const b{at} Bool)", f"(assert (= b{at} {formula}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'b{at}' for at in range(len(formulas)))}))"]
    answer = subprocess.run(
        ["cvc5", "--produce-models", "--lang", "smt", "--quiet"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert answer.startswith("sat"), answer
    return [value == "true" for value in re.findall(r"\(b\d+ (true|false)\)", answer)]


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_order_written_letter_by_letter() -> None:
    triples = _triples(400)
    formulas = []
    for value, op, literal in triples:
        side, or_equal, _ = PYTHON_ORDERS[op]
        formulas.append(side(encode(value), literal, or_equal=or_equal))

    truths = _truths(formulas)

    python = [PYTHON_ORDERS[op][2](value, literal) for value, op, literal in triples]
    disagreements = [
        triple for triple, said, meant in zip(triples, truths, python, strict=True) if said != meant
    ]
    assert disagreements == []


@needs_cvc5
def test_four_orders_against_single_letters_are_decided_at_once() -> None:
    # cvc5's own str.< ran this prefix to any time limit while every three of the four
    # answered unsat in milliseconds; letter by letter, the four answer unsat too
    prefix = (
        Branch(expression=["<", "s", "'b'"], taken=False, site=SITE),
        Branch(expression=["<=", "s", "'c'"], taken=False, site=SITE),
        Branch(expression=[">", "s", "'d'"], taken=False, site=SITE),
        Branch(expression=[">=", "s", "'e'"], taken=True, site=SITE),
    )

    assert solve(prefix, {"s": str}, 1.0) == Unsat()
