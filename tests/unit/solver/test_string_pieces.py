"""The pieces in SMT-LIB: the terms strings.py writes, and cvc5 held against Python on them."""

import operator
import random
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import (
    character,
    encode,
    replaced,
    sliced,
    without_prefix,
    without_suffix,
)
from tests.unit.solver.agreement import (
    ALPHABET,
    PATH_LETTERS,
    SITE,
    asked,
    disagrees,
    flipped_path,
    heads_named,
    needs_cvc5,
)
from tests.unit.solver.test_render import render

# the bounds a random slice picks from: missing, negative, and past either end of a string of
# up to five characters
BOUNDS: list[int | None] = [None, *range(-7, 8)]


def test_a_negative_index_counts_back_from_the_end() -> None:
    assert character("s", 2) == "(str.at s 2)"
    assert character("s", -1) == "(str.at s (- (str.len s) 1))"


def test_a_slice_clamps_a_start_that_counts_back_past_the_beginning() -> None:
    back = "(- (str.len s) 2)"
    start = f"(ite (< {back} 0) 0 {back})"

    assert sliced("s", -2, None) == f"(str.substr s {start} (- (str.len s) {start}))"


def test_a_slice_with_both_bounds_missing_is_the_whole_string() -> None:
    assert sliced("s", None, None) == "(str.substr s 0 (- (str.len s) 0))"


def test_a_removed_prefix_or_suffix_reads_a_literal_length_as_a_number() -> None:
    assert without_prefix("s", '"ab"') == (
        '(ite (str.prefixof "ab" s) (str.substr s 2 (- (str.len s) 2)) s)'
    )
    assert without_suffix("s", '"ab"') == (
        '(ite (str.suffixof "ab" s) (str.substr s 0 (- (str.len s) 2)) s)'
    )


# `s[1:][1:]`, a piece of a piece
TWICE_CUT: Expression = ["[:]", ["[:]", "s", 1, None], 1, None]

# each search and order that reads its string more than once, on a piece
READ_MORE_THAN_ONCE: dict[str, Expression] = {
    "rfind": [">", ["rfind", TWICE_CUT, "'x'"], 0],
    "count": [">", ["count", TWICE_CUT, "'x'"], 0],
    "<": ["<", TWICE_CUT, "'abcd'"],
    ">=": [">=", TWICE_CUT, "'abcd'"],
    "rfind-a-piece": [">", ["rfind", "t", TWICE_CUT], 0],
    "count-a-piece": [">", ["count", "t", TWICE_CUT], 0],
}


@pytest.mark.parametrize("condition", READ_MORE_THAN_ONCE.values(), ids=list(READ_MORE_THAN_ONCE))
def test_a_search_or_an_order_writes_a_piece_once(condition: Expression) -> None:
    text = render((Branch(expression=condition, taken=True, site=SITE),), {"s": str, "t": str})

    # the form reads the piece several times, and the program defines it once for all of them
    assert text.count(sliced("|arg.s|", 1, None)) == 1
    assert text.count(sliced("e!0", 1, None)) == 1
    assert "e!1" in text.split("(assert ")[-1]


def _value(rng: random.Random, longest: int) -> str:
    return "".join(rng.choices(ALPHABET, k=rng.randint(0, longest)))


def _cut(rng: random.Random, value: str, longest: int) -> str:
    """A random string, or half the time one cut from the value, so a match is as likely."""
    if value and rng.random() < 0.5:
        start = rng.randint(0, len(value) - 1)
        return value[start : start + rng.randint(0, longest)]
    return _value(rng, longest)


# how a case writes its other string: as a literal, or as a constant held equal to one, the way
# a tracked str reaches a form
type Written = Callable[[str], str]
# a case: the term to ask of the string in a constant, and Python's answer
type Case = tuple[Callable[[str], str], str]


def _index_case(rng: random.Random, value: str, _: Written) -> Case:
    # an index answers only past its long-enough fork, so it is always in range here
    index = rng.randint(-len(value), len(value) - 1)
    return (lambda s: character(s, index)), value[index]


def _slice_case(rng: random.Random, value: str, _: Written) -> Case:
    start, stop = rng.choice(BOUNDS), rng.choice(BOUNDS)
    return (lambda s: sliced(s, start, stop)), value[start:stop]


def _replace_case(rng: random.Random, value: str, held: Written) -> Case:
    # a literal old string with at least one character: any other old string is a downgrade
    old = _cut(rng, value, 2) or rng.choice(ALPHABET)
    new = _value(rng, 2)
    written = held(new)
    return (lambda s: replaced(s, encode(old), written)), value.replace(old, new)


def _prefix_case(rng: random.Random, value: str, held: Written) -> Case:
    prefix = value[: rng.randint(0, 2)] if rng.random() < 0.5 else _value(rng, 2)
    written = held(prefix)
    return (lambda s: without_prefix(s, written)), value.removeprefix(prefix)


def _suffix_case(rng: random.Random, value: str, held: Written) -> Case:
    suffix = value[len(value) - rng.randint(0, 2) :] if rng.random() < 0.5 else _value(rng, 2)
    written = held(suffix)
    return (lambda s: without_suffix(s, written)), value.removesuffix(suffix)


def _concatenation_case(rng: random.Random, value: str, held: Written) -> Case:
    other = _value(rng, 2)
    written = held(other)
    if rng.random() < 0.5:
        return (lambda s: f"(str.++ {s} {written})"), value + other
    return (lambda s: f"(str.++ {written} {s})"), other + value


MAKERS = [
    _index_case,
    _slice_case,
    _replace_case,
    _prefix_case,
    _suffix_case,
    _concatenation_case,
]


def _program(count: int) -> tuple[list[str], list[str]]:
    """One program asking the answer of every case, and Python's answers, fixed by the seed.

    Each value is a constant held equal to its literal, so the string reaches
    the form as a name, the way a tracked parameter does.
    """
    rng = random.Random(0)
    lines = ["(set-logic ALL)"]
    python: list[str] = []
    for at in range(count):
        maker = MAKERS[at % len(MAKERS)]
        value = _value(rng, 5) or (rng.choice(ALPHABET) if maker is _index_case else "")
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        term, answer = maker(rng, value, _holder(rng, lines, at))
        lines += [f"(declare-const v{at} String)", f"(assert (= v{at} {term(f's{at}')}))"]
        python.append(answer)
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(count))}))"]
    return lines, python


def _holder(rng: random.Random, lines: list[str], at: int) -> Written:
    """How case ``at`` writes its other string: a literal, or three times in ten a constant."""
    tracked = rng.random() < 0.3

    def held(value: str) -> str:
        if not tracked:
            return encode(value)
        lines.extend([f"(declare-const t{at} String)", f"(assert (= t{at} {encode(value)}))"])
        return f"t{at}"

    return held


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_piece() -> None:
    lines, python = _program(600)

    answers = asked(lines)

    # every value is fixed, so cvc5 only works each term out: this holds the terms to Python
    assert len(answers) == len(python)
    disagreements = [
        (at, said, meant)
        for at, (said, meant) in enumerate(zip(answers, python, strict=True))
        if said != meant
    ]
    assert disagreements == []


# a replace whose old string overlaps itself in the value, so only replacing left to right
# without overlap gives Python's answer: the value, the old string, and the new one
OVERLAPPING = [("aaaaa", "aa", "b"), ("ababa", "aba", "x")]


@needs_cvc5
def test_cvc5_replaces_an_old_string_that_overlaps_itself_as_python_does() -> None:
    lines = ["(set-logic ALL)"]
    for at, (value, old, new) in enumerate(OVERLAPPING):
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        lines += [f"(declare-const t{at} String)", f"(assert (= t{at} {encode(new)}))"]
        # the new string as a literal, and as a constant, the way a tracked str reaches the form
        for asked_at, written in ((2 * at, encode(new)), (2 * at + 1, f"t{at}")):
            term = replaced(f"s{at}", encode(old), written)
            lines += [f"(declare-const v{asked_at} String)", f"(assert (= v{asked_at} {term}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(4))}))"]

    # each case is asked twice, the new string a literal and then a constant
    python = [value.replace(old, new) for value, old, new in OVERLAPPING for _ in range(2)]
    assert asked(lines) == python


# the pieces that take a str to remove, and the term each is written as
AFFIXES: dict[str, Callable[[str, str], str]] = {
    "removeprefix": without_prefix,
    "removesuffix": without_suffix,
}


def _affix_case(rng: random.Random, at: int) -> tuple[list[str], str]:
    """`s[1:].removeprefix(t[1:])` or the suffix alike: the lines asking it, and Python's answer.

    Both operands are pieces, written in full here. Most of the time t[1:]
    is cut from the end of s[1:] it names, so about a third of the cases
    remove something.
    """
    head = rng.choice(list(AFFIXES))
    value = _value(rng, 5)
    kept, cut = value[1:], rng.randint(0, 2)
    end = kept[:cut] if head == "removeprefix" else kept[len(kept) - cut :]
    other = rng.choice(ALPHABET) + (end if rng.random() < 0.6 else _value(rng, 2))
    term = AFFIXES[head](sliced(f"s{at}", 1, None), sliced(f"t{at}", 1, None))
    lines = [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
    lines += [f"(declare-const t{at} String)", f"(assert (= t{at} {encode(other)}))"]
    lines += [f"(declare-const v{at} String)", f"(assert (= v{at} {term}))"]
    return lines, getattr(str, head)(kept, other[1:])


@needs_cvc5
def test_cvc5_agrees_with_python_when_a_piece_removes_a_piece() -> None:
    rng = random.Random(1)
    cases = [_affix_case(rng, at) for at in range(120)]
    lines = ["(set-logic ALL)", *(line for case, _ in cases for line in case)]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]

    assert asked(lines) == [answer for _, answer in cases]


# what each head on a piece path means in Python, to hold a model against the plan
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    "[]": operator.getitem,
    "[:]": lambda s, start, stop: s[start:stop],
    "+": operator.add,
    "replace": str.replace,
    "removeprefix": str.removeprefix,
    "removesuffix": str.removesuffix,
    "len": len,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    ">=": operator.ge,
}

# the pieces a random path picks from
PIECE_HEADS = ("[]", "[:]", "+", "replace", "removeprefix", "removesuffix")


def _literal(rng: random.Random, longest: int) -> str:
    return repr("".join(rng.choices(PATH_LETTERS, k=rng.randint(0, longest))))


def piece_of(
    rng: random.Random, receiver: Expression = "s", heads: tuple[str, ...] = PIECE_HEADS
) -> tuple[Expression, Expression | None]:
    """One random piece of the receiver, and the fork an index records before it, if any."""
    head = rng.choice(heads)
    if head == "[]":
        index = rng.randint(-3, 2)
        measured: Expression = ["len", receiver]
        fork: Expression = [">", measured, index] if index >= 0 else [">=", measured, -index]
        return ["[]", receiver, index], fork
    if head == "[:]":
        bounds = [rng.choice([None, -2, 0, 1, 3]), rng.choice([None, -1, 2, 4])]
        return ["[:]", receiver, *bounds], None
    if head == "+":
        pair: list[Expression] = [receiver, _literal(rng, 2)]
        return ["+", *(pair if rng.random() < 0.5 else pair[::-1])], None
    if head == "replace":
        return ["replace", receiver, repr(rng.choice(PATH_LETTERS)), _literal(rng, 2)], None
    return [head, receiver, _literal(rng, 2)], None


# the pieces that record no fork, so one can be taken of another piece or joined to one
UNFORKED_HEADS = tuple(head for head in PIECE_HEADS if head != "[]")


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some string takes through random compares on pieces, the last one flipped."""
    s = "".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 5)))
    pieces = (_compared(rng) for _ in range(rng.randint(1, 5)))
    return flipped_path(s, pieces, PYTHON_HEADS)


def _compared(rng: random.Random) -> tuple[Expression, Expression | None]:
    """A random piece compared with a literal, and the fork the piece records first, if any.

    A third of the time the piece is taken of another piece, and a fifth of
    the time it is joined to a second piece of s, so a `+` has no name and no
    literal on either side.
    """
    term, long_enough = piece_of(rng)
    if rng.random() < 0.3:
        term, _ = piece_of(rng, term, UNFORKED_HEADS)
    if rng.random() < 0.2:
        term = ["+", term, piece_of(rng, "s", UNFORKED_HEADS)[0]]
    return [rng.choice(["==", "!=", "<", ">="]), term, _literal(rng, 2)], long_enough


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_piece_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [_flipped_path(rng) for _ in range(40)]

    answers = [solve(path, {"s": str}, 2.0) for path in paths]

    # an error is cvc5 failing to answer at all, which is never agreement
    assert [answer for answer in answers if isinstance(answer, Error)] == []
    # the paths cvc5 answered reach every piece, so a clean result is not a narrow one
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    assert set().union(*(heads_named(path, PIECE_HEADS) for path in answered)) == set(PIECE_HEADS)
    # a timeout or an unknown is a miss, which the run reports as one; only an answer can be
    # wrong, so a miss fails this test only by leaving a piece unanswered
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if disagrees(path, answer, PYTHON_HEADS, [*PATH_LETTERS, "z"], 5)
    ]
    assert wrong == []


def _walk(step: int, index: int) -> list[tuple[Expression, Expression | None]]:
    """Thirty passes of a loop that tests one end of s and cuts it off, `s = s[1:]` or `s[:-1]`.

    Each pass tests s for truth, then the character at ``index``, after the
    fork the index records first.
    """
    term: Expression = "s"
    conditions: list[tuple[Expression, Expression | None]] = []
    for _ in range(30):
        measured: Expression = ["len", term]
        long_enough: Expression = [">", measured, index] if index >= 0 else [">=", measured, 1]
        conditions.append((["!=", term, "''"], None))
        conditions.append((["==", ["[]", term, index], "'x'"], long_enough))
        term = ["[:]", term, 1, None] if step > 0 else ["[:]", term, None, -1]
    return conditions


@needs_cvc5
@pytest.mark.parametrize(("step", "index"), [(1, 0), (-1, -1)], ids=["s = s[1:]", "s = s[:-1]"])
def test_cvc5_agrees_with_python_on_a_walk_thirty_pieces_deep(step: int, index: int) -> None:
    # thirty letters, none of them x, and the last pass's compare flipped: the answer needs an
    # x thirty pieces down
    path = flipped_path("ab" * 15, _walk(step, index), PYTHON_HEADS)

    answer = solve(path, {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    assert not disagrees(path, answer, PYTHON_HEADS, [], 0)
