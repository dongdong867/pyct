"""cvc5 held against Python where a string is read as a number: `int(s)` and `float(s)`."""

import re
import statistics
import sys
import time
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver import numerals
from pyct.solver.answer import Answer, Unsat
from pyct.solver.cvc5 import Sat, solve
from pyct.solver.floats import literal
from pyct.solver.strings import encode
from tests.unit.solver.agreement import SITE, needs_cvc5
from tests.unit.solver.test_float_agreement import _same
from tests.unit.solver.test_float_int_agreement import _values
from tests.unit.solver.test_render import render

# texts Python reads as an int, and texts it refuses, around each rule of its grammar: the spaces
# it strips, a sign, underscores between digits, and the digits it counts against its limit
INT_TEXTS = [
    "0",
    "7",
    "-7",
    "+7",
    " 12 ",
    "\t-1_0\n",
    "\x0b\x0c\r3",
    "007",
    "0_0",
    "1_000_000",
    "9" * 30,
    "",
    " ",
    "+",
    "-",
    "_1",
    "1_",
    "1__0",
    "+_1",
    "1 2",
    "- 1",
    "+-1",
    "--1",
    "\x1c1",
    "1e3",
    "0x10",
    "12a",
    "1.0",
]

# texts Python reads as a float and texts it refuses: each form of a decimal, an exponent, the
# infinities and NaN in any case, underscores, spaces, and values that round
FLOAT_TEXTS = [
    "0",
    "-0",
    "1.5",
    "-1.5",
    ".5",
    "5.",
    "-.5",
    "0.1",
    "123.456",
    "0.30000000000000004",
    "9007199254740993",
    "9007199254740993.5",
    "1" * 400,
    "1e5",
    "1E-5",
    "5.e3",
    "  2.5  ",
    "1_0.5",
    "1.5_0",
    "1e1_0",
    "1_000.000_1e+0_1",
    "1e400",
    "1e-400",
    "4.9e-324",
    "inf",
    "-inf",
    "+Infinity",
    "iNfInItY",
    "nan",
    "-nan",
    "NaN",
    "0.0000000000000000000001",
    "",
    ".",
    "-.",
    "1._5",
    "1e",
    "e1",
    "1.5.2",
    "infinit",
    "nan1",
    "1 .5",
    "0x1p3",
    "\x1c1.5",
]


def _read(read: type, text: str) -> object:
    try:
        return read(text)
    except ValueError:
        return None


# the texts float_of reads exactly: digits, a point and a fraction, after a minus, and nan and inf
_PLAIN = re.compile(r"-?(\d+(\.\d*)?|\.\d+|nan|inf)", re.ASCII)


def _inside(text: str) -> bool:
    """Whether a text is inside the bound float_of is exact in, as Python has it."""
    if _PLAIN.fullmatch(text) is None:
        return False
    whole, _, fraction = text.removeprefix("-").partition(".")
    if text.removeprefix("-") in ("nan", "inf") or not fraction:
        return True
    return len(fraction) <= 22 and int(whole + fraction) <= 2**53


@needs_cvc5
def test_cvc5_accepts_exactly_the_ascii_texts_python_reads_as_an_int() -> None:
    said = _values("Bool", [numerals.is_int(encode(text)) for text in INT_TEXTS])

    assert said == [_read(int, text) is not None for text in INT_TEXTS]


@needs_cvc5
def test_cvc5_reads_each_int_text_as_python_does() -> None:
    texts = [text for text in INT_TEXTS if _read(int, text) is not None]

    said = _values("Int", [numerals.int_of(encode(text)) for text in texts])

    assert said == [int(text) for text in texts]


def test_python_counts_the_digits_of_an_int_text_against_its_limit() -> None:
    most = sys.get_int_max_str_digits()

    # the digits alone count: leading zeros do, and underscores, spaces and a sign do not
    assert int("1" * most) > 0
    assert int(" -" + "1_" * (most - 1) + "1 ") < 0
    for past in ("1" * (most + 1), "0" * (most + 1)):
        with pytest.raises(ValueError, match="Exceeds the limit"):
            int(past)


@needs_cvc5
@pytest.mark.parametrize(
    ("most", "held"),
    [(5, [True, True, True, False, False]), (0, [True] * 5)],
)
def test_cvc5_counts_the_digits_of_an_int_text_as_python_does(
    monkeypatch: pytest.MonkeyPatch, most: int, held: list[bool]
) -> None:
    # a limit of five stands in for Python's 4300, which cvc5 reads slowly; zero is no limit
    monkeypatch.setattr(sys, "get_int_max_str_digits", lambda: most)
    texts = ["12345", "1_2_3_4_5", " -12345 ", "123456", "000001"]

    said = _values("Bool", [numerals.is_int(encode(text)) for text in texts])

    assert said == held


# ints whose text cvc5 writes: zero, each sign, a power of ten, and one past a machine word
TEXT_INTS = [0, 7, -7, -42, 10, 90, -100, 10**25, -(10**25) - 1]


def _int_term(value: int) -> str:
    return f"(- {-value})" if value < 0 else str(value)


@needs_cvc5
def test_cvc5_writes_each_int_as_python_writes_it() -> None:
    said = _values("String", [numerals.text_of_int(_int_term(value)) for value in TEXT_INTS])

    assert said == [str(value) for value in TEXT_INTS]


@needs_cvc5
def test_cvc5_writes_a_bool_as_python_writes_it() -> None:
    said = _values("String", [numerals.text_of_bool(term) for term in ("true", "false")])

    assert said == [str(True), str(False)]


@needs_cvc5
@pytest.mark.parametrize(
    ("expression", "holds"),
    [
        pytest.param(["==", ["str", "n"], "'-42'"], lambda n: str(n) == "-42", id="equal"),
        pytest.param(
            ["startswith", ["str", "n"], "'9'"], lambda n: str(n).startswith("9"), id="prefix"
        ),
        pytest.param(["==", ["len", ["str", "n"]], 3], lambda n: len(str(n)) == 3, id="length"),
    ],
)
def test_cvc5_finds_an_int_whose_text_python_writes_so(
    expression: Expression, holds: Callable[[int], bool]
) -> None:
    fork = Branch(expression=expression, taken=True, site=Site(file="m.py", line=2, col=7))

    answer = solve((fork,), {"n": int}, 10.0)

    assert isinstance(answer, Sat), answer
    value = answer.model["n"]
    assert isinstance(value, int)
    assert holds(value)


@needs_cvc5
def test_a_text_past_ascii_reads_as_no_number() -> None:
    # Python reads Arabic-Indic digits and a no-break space; the encoding is exact for ASCII
    texts = ["١٢", "\xa012"]

    said = _values("Bool", [numerals.is_int(encode(text)) for text in texts])

    assert said == [False, False]
    assert [int(text) for text in texts] == [12, 12]


@needs_cvc5
def test_cvc5_accepts_exactly_the_ascii_texts_python_reads_as_a_float() -> None:
    said = _values("Bool", [numerals.is_float(encode(text)) for text in FLOAT_TEXTS])

    assert said == [_read(float, text) is not None for text in FLOAT_TEXTS]


@needs_cvc5
def test_cvc5_reads_each_float_text_inside_its_bound_as_python_does_to_the_bit() -> None:
    texts = [text for text in FLOAT_TEXTS if _read(float, text) is not None]
    written = [numerals.float_of(encode(text), "past") for text in texts]

    values = _values("Float64", [term for term, _ in written], "(declare-const past Float64)")
    bounds = _values("Bool", [bound for _, bound in written], "(declare-const past Float64)")

    assert bounds == [_inside(text) for text in texts]
    wrong = [
        (text, value)
        for text, value, inside in zip(texts, values, bounds, strict=True)
        if inside and not _same(value, float(text))
    ]
    assert wrong == []
    # the texts reach past the bound too, so a clean result is not a narrow one
    assert False in bounds


@needs_cvc5
def test_past_its_bound_float_of_a_text_can_be_every_value_python_reads() -> None:
    texts = [text for text in FLOAT_TEXTS if _read(float, text) is not None]
    texts = [text for text in texts if not _inside(text)]
    written = [numerals.float_of(encode(text), literal(float(text))) for text in texts]

    values = _values("Float64", [term for term, _ in written])

    assert [_same(value, float(text)) for value, text in zip(values, texts, strict=True)] == [
        True
    ] * len(texts)


@needs_cvc5
def test_without_a_constant_past_its_bound_float_of_a_text_is_the_exact_term() -> None:
    term, bound = numerals.float_of(encode("2.5"))

    assert _values("Float64", [term]) == [2.5]
    assert _values("Bool", [bound]) == [True]


@needs_cvc5
def test_cvc5_reads_one_character_as_python_does() -> None:
    characters = [chr(code) for code in range(128)]
    digits = [character for character in characters if _read(int, character) is not None]

    accepted = _values("Bool", [numerals.is_int_character(encode(c)) for c in characters])
    read = _values("Int", [numerals.int_of_character(encode(c)) for c in digits])

    assert accepted == [_read(int, character) is not None for character in characters]
    assert read == [int(character) for character in digits]


def _read_as_int(text: Expression) -> tuple[Branch, ...]:
    """The forks of `int(text)` on a string Python reads, and of the int above 4."""
    return (
        Branch(expression=["isint", text], taken=True, site=SITE),
        Branch(expression=[">", ["int", text], 4], taken=True, site=SITE),
    )


def test_a_character_of_a_string_is_read_as_one_digit() -> None:
    """A loop's case, `int(ch)` for each character: no pass over the text, which cost cvc5
    seconds for each character the path read."""
    text = render(_read_as_int(["[]", "s", 3]), {"s": str})

    assert '(str.in_re e!0 (re.range "0" "9"))' in text
    assert "(str.to_int e!0)" in text
    assert "str.replace_re_all" not in text


def test_a_piece_of_a_split_is_read_by_the_whole_grammar() -> None:
    """A piece Python builds holds any number of characters, as a version's parts do."""
    text = render(_read_as_int(["[]", ["split", "s", "'.'"], 0]), {"s": str})

    assert "str.replace_re_all" in text


@needs_cvc5
def test_a_digit_string_never_reads_as_a_negative_int() -> None:
    """A version's case: a part of digits whose int is neither zero nor above it."""
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=["isint", "s"], taken=True, site=SITE),
        Branch(expression=["==", ["int", "s"], 0], taken=False, site=SITE),
        Branch(expression=[">", ["int", "s"], 0], taken=False, site=SITE),
    )

    assert isinstance(solve(prefix, {"s": str}, 5.0), Unsat)


def _asked_seconds(prefix: tuple[Branch, ...]) -> tuple[Answer, float]:
    """The answer to a path, and the median of three solve times in seconds."""
    times: list[float] = []
    answer: Answer | None = None
    for _ in range(3):
        start = time.monotonic()
        answer = solve(prefix, {"s": str}, 10.0)
        times.append(time.monotonic() - start)
    assert answer is not None
    return answer, statistics.median(times)


@needs_cvc5
@pytest.mark.parametrize("value", [100000, 200000])
def test_a_digit_string_of_at_most_five_characters_never_reads_as_six_digits_fast(
    value: int,
) -> None:
    """The negated row's case: an int no string of at most five digits reads, answered in time
    for the shallow forks after it."""
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=[">", ["len", "s"], 5], taken=False, site=SITE),
        Branch(expression=["isint", "s"], taken=True, site=SITE),
        Branch(expression=["==", ["int", "s"], value], taken=True, site=SITE),
    )

    answer, seconds = _asked_seconds(prefix)

    assert isinstance(answer, Unsat), answer
    assert seconds < 0.5


@needs_cvc5
def test_the_fact_about_an_int_text_holds_for_every_text() -> None:
    texts = [*INT_TEXTS, *(chr(code) for code in range(128)), "9" * 20, "1" + "0" * 20, "٣"]

    said = _values("Bool", [numerals.int_fact(encode(text)) for text in texts])

    assert said == [True] * len(texts)


@needs_cvc5
def test_a_digit_string_of_at_most_five_characters_is_always_read_as_an_int_fast() -> None:
    """The negated row's other case: no string of at most five digits is one `int` refuses."""
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=[">", ["len", "s"], 5], taken=False, site=SITE),
        Branch(expression=["isint", "s"], taken=False, site=SITE),
    )

    answer, seconds = _asked_seconds(prefix)

    assert isinstance(answer, Unsat), answer
    assert seconds < 0.5
