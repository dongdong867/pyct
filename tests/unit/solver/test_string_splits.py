"""The pieces of a split in SMT-LIB: each piece's term and whether the string has it, and cvc5
held against Python on them."""

import random
import sys
import time
import tracemalloc
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LONGEST_WALK
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.splits import SPLITS
from pyct.solver.strings import encode
from tests.unit.solver.agreement import (
    SITE,
    ascii_disagrees,
    asked,
    flipped_path,
    method,
    needs_cvc5,
    python,
)
from tests.unit.solver.test_render import render

# the characters random strings are made of: the separators here, whitespace and line breaks,
# and letters; the separators, one that overlaps itself among them
COMMON = list("ab ,\t\n\r\x0b\x0c\x1c\x1f=")
# the line breaks past ASCII, where splitlines breaks as Python does and a split on whitespace
# reads none of them
BREAKS_PAST_ASCII = ["\x85", "\u2028", "\u2029"]
SEPARATORS = [",", " ", "ab", "aa", "\n"]

# a split: its head, the plain operands after the string, and the pieces Python makes
type Split = tuple[str, tuple[object, ...], list[str]]


def _split(rng: random.Random, value: str) -> Split:
    head = rng.choice(list(SPLITS))
    if head == "partition":
        separator = rng.choice(SEPARATORS)
        return head, (separator,), list(value.partition(separator))
    if head == "splitlines":
        operands: tuple[object, ...] = rng.choice([(), (False,), (True,)])
        return head, operands, value.splitlines(*operands)  # pyrefly: ignore[no-matching-overload]
    separator = rng.choice([None, *SEPARATORS])
    if head == "rsplit" and separator == "aa":
        # core hands an rsplit on a separator that overlaps itself on only with a limit
        operands = (separator, rng.randint(0, 2))
    else:
        # a limit past the longest walk reads as no limit, on strings with fewer separators
        limit = rng.choice([-1, 0, 1, 2, LONGEST_WALK + 1])
        operands = rng.choice([(), (separator,), (separator, limit)])
    return head, operands, getattr(value, head)(*operands)


def _program(cases: list[tuple[str, Split, int]]) -> tuple[list[str], list[object]]:
    """One program asking whether each value has its piece, and the piece when it does."""
    lines = ["(set-logic ALL)"]
    python: list[object] = []
    for at, (value, (head, operands, pieces), index) in enumerate(cases):
        piece, there = SPLITS[head](f"s{at}", operands, index)
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        asked_now: list[tuple[str, str, object]] = [("Bool", there, index < len(pieces))]
        if index < len(pieces):
            asked_now.append(("String", piece, pieces[index]))
        for sort, term, answer in asked_now:
            name = f"v{len(python)}"
            lines += [f"(declare-const {name} {sort})", f"(assert (= {name} {term}))"]
            python.append(answer)
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(python)))}))"]
    return lines, python


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_piece_of_every_split() -> None:
    rng = random.Random(0)
    cases: list[tuple[str, Split, int]] = []
    for _ in range(600):
        value = "".join(rng.choices(COMMON, k=rng.randint(0, 8)))
        split = _split(rng, value)
        cases.append((value, split, rng.randint(0, _highest(split))))
    lines, python = _program(cases)

    assert asked(lines) == python


def _highest(split: Split) -> int:
    """The highest position asked of a split: a split with a limit has at most limit + 1
    pieces, and core writes no position past them."""
    head, operands, _ = split
    limit = operands[1] if len(operands) > 1 else -1
    if head == "partition":
        return 2
    return limit if isinstance(limit, int) and 0 <= limit < 4 else 4


@needs_cvc5
def test_cvc5_breaks_lines_past_ascii_where_python_does() -> None:
    rng = random.Random(1)
    cases: list[tuple[str, Split, int]] = []
    for _ in range(150):
        value = "".join(rng.choices([*COMMON, *BREAKS_PAST_ASCII], k=rng.randint(0, 8)))
        operands: tuple[object, ...] = rng.choice([(), (False,), (True,)])
        lines = value.splitlines(*operands)  # pyrefly: ignore[no-matching-overload]
        cases.append((value, ("splitlines", operands, lines), rng.randint(0, 3)))
    program, python = _program(cases)

    assert asked(program) == python


BAD_OPERANDS: dict[str, tuple[str, tuple[object, ...]]] = {
    "a split on an int": ("split", (1,)),
    "a split to a str limit": ("split", (",", "1")),
    "an rsplit on an int": ("rsplit", (1, 1)),
    "a partition on None": ("partition", (None,)),
}


@pytest.mark.parametrize(("head", "operands"), BAD_OPERANDS.values(), ids=list(BAD_OPERANDS))
def test_a_split_on_operands_core_never_writes_is_an_error(
    head: str, operands: tuple[object, ...]
) -> None:
    with pytest.raises(ValueError, match="core writes"):
        SPLITS[head]("s", operands, 0)


def fork(expression: Expression, *, taken: bool) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def test_a_piece_asserts_once_that_the_string_has_it() -> None:
    split: Expression = ["split", "s", "','"]
    second: Expression = ["[]", split, 1]
    prefix = (
        fork(["==", second, "'a'"], taken=False),
        fork(["==", ["+", ["[]", split, 0], second], "'ab'"], taken=False),
    )

    lines = render(prefix, {"s": str}).splitlines()

    _, there = SPLITS["split"]("|arg.s|", (",",), 1)
    # the path took piece 1 twice; the string has it on every input that follows the path
    assert lines.count(f"(assert {there})") == 1
    # two pieces of a split side by side are two strings, not a slice of the list
    assert "str.substr |arg.s| 0 2" not in "\n".join(lines)


# pieces every string has: partition's three, and the first of a split or rsplit on a separator
ALWAYS_THERE: dict[str, Expression] = {
    "partition": ["[]", ["partition", "s", "','"], 2],
    "split": ["[]", ["split", "s", "','", 2], 0],
    "rsplit": ["[]", ["rsplit", "s", "','", 2], 0],
}


@pytest.mark.parametrize("piece", ALWAYS_THERE.values(), ids=list(ALWAYS_THERE))
def test_a_piece_the_string_always_has_asserts_nothing(piece: Expression) -> None:
    prefix = (fork(["==", piece, "'a'"], taken=True),)

    lines = render(prefix, {"s": str}).splitlines()

    assert [line for line in lines if line.startswith("(assert ")] == [lines[-3]]


def test_a_piece_at_a_position_that_is_not_an_int_is_an_error() -> None:
    prefix = (fork(["==", ["[]", ["split", "s"], None], "'a'"], taken=True),)

    with pytest.raises(ValueError, match="piece None"):
        render(prefix, {"s": str})


# what each head on a split path means in Python; a piece the string does not have raises
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    **{head: method(head) for head in SPLITS},
    "[]": lambda pieces, index: pieces[index],
    "upper": str.upper,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

LETTERS: list[str] = list("ab ,\n")


def _compared(rng: random.Random, s: str) -> tuple[Expression, Expression | None]:
    """A random piece of a split of s, or of s uppercased, compared with a literal.

    The piece is one s has, as it is for the target that took it out.
    """
    receiver: Expression = "s" if rng.random() < 0.8 else ["upper", "s"]
    head, operands, pieces = _split(rng, s.upper() if receiver != "s" else s)
    index = rng.randint(0, max(len(pieces) - 1, 0))
    written = [_written(part) for part in operands]
    literal = repr("".join(rng.choices(LETTERS, k=rng.randint(0, 2))))
    return [rng.choice(["==", "!="]), ["[]", [head, receiver, *written], index], literal], None


def _written(operand: object) -> Expression:
    """A plain operand of a split as core writes it: a literal, None, or an int or bool."""
    if isinstance(operand, str):
        return repr(operand)
    assert operand is None or isinstance(operand, int), operand
    return operand


def _split_head(expression: Expression) -> str:
    """The split a compare of one of its pieces reads."""
    match expression:
        case [_, ["[]", [str() as head, *_], _], _]:
            return head
    raise AssertionError(expression)


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_split_path_it_answers() -> None:
    rng = random.Random(0)
    paths = []
    for _ in range(60):
        s = "".join(rng.choices(LETTERS, k=rng.randint(1, 6)))
        conditions = [_compared(rng, s) for _ in range(rng.randint(1, 3))]
        if all(_has(condition, s) for condition, _ in conditions):
            paths.append(flipped_path(s, conditions, PYTHON_HEADS))

    answers = [solve(path, {"s": str}, 2.0) for path in paths]

    assert [answer for answer in answers if isinstance(answer, Error)] == []
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    assert {_split_head(fork.expression) for path in answered for fork in path} == set(SPLITS)
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if ascii_disagrees(path, answer, PYTHON_HEADS, LETTERS, 3)
    ]
    assert wrong == []


def _has(condition: Expression, s: str) -> bool:
    """Whether s has the piece a condition reads, as the target that took it out had it."""
    try:
        python(condition, s, PYTHON_HEADS)
    except IndexError:
        return False
    return True


def test_an_operand_that_opens_with_a_quote_but_holds_no_str_is_an_error() -> None:
    prefix = (fork(["==", ["center", "s", 5, "'*', '-'"], "'a'"], taken=True),)

    with pytest.raises(ValueError, match="not a string literal"):
        render(prefix, {"s": str})


@pytest.mark.parametrize("separator", ["','", None], ids=["on a separator", "on whitespace"])
def test_an_rsplit_with_a_large_limit_renders_in_size_and_memory_that_grow_with_it(
    separator: str | None,
) -> None:
    def rendered(limit: int) -> str:
        condition: Expression = ["==", ["[]", ["rsplit", "s", separator, limit], 0], "'a'"]
        return render((fork(condition, taken=False),), {"s": str})

    tracemalloc.start()
    started = time.perf_counter()
    text = rendered(2000)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # the reversed string is walked once, each step naming the last, so twice the limit is
    # about twice the text: 0.6 MB on a separator and 1.7 MB on whitespace at 2,000
    assert len(text) < 2.2 * len(rendered(1000))
    assert len(text) < 2_000_000
    assert elapsed < 1.0
    assert peak < 20_000_000


@pytest.mark.parametrize("head", ["rsplit", "split"])
@pytest.mark.parametrize("separator", ["','", None], ids=["on a separator", "on whitespace"])
def test_a_split_with_the_largest_limit_python_takes_renders_at_once(
    head: str, separator: str | None
) -> None:
    condition: Expression = ["==", ["[]", [head, "s", separator, sys.maxsize], 1], "'a'"]

    started = time.perf_counter()
    text = render((fork(condition, taken=False),), {"s": str})

    # past the longest walk, a piece is read as the split's with no limit, so the limit's
    # size costs nothing
    assert time.perf_counter() - started < 0.5
    assert len(text) < 20_000


# a string with as many separators, or words, as an rsplit past the longest walk allows, and
# one with more: an rsplit and a split agree on the first, and the second is no answer
PAST_THE_WALK: dict[str, tuple[str | None, str, bool]] = {
    "as many separators": (",", "," * (LONGEST_WALK + 1), True),
    "one separator more": (",", "," * (LONGEST_WALK + 2), False),
    "fewer words": (None, "a " * LONGEST_WALK, True),
    "as many words": (None, "a " * (LONGEST_WALK + 1), False),
}


@needs_cvc5
@pytest.mark.parametrize(
    ("separator", "value", "there"), PAST_THE_WALK.values(), ids=list(PAST_THE_WALK)
)
def test_an_rsplit_past_the_walk_is_an_answer_only_where_it_is_the_split(
    separator: str | None, value: str, there: bool
) -> None:
    limit = LONGEST_WALK + 1
    split: Split = ("rsplit", (separator, limit), value.rsplit(separator, limit))
    lines, python = _program([(value, split, 0)])

    answers = asked(lines)

    assert answers[0] is there
    if there:
        assert answers == python
