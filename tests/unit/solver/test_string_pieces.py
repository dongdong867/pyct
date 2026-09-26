"""The pieces in SMT-LIB: the terms strings.py writes, and cvc5 held against Python on them."""

import operator
import random
from collections.abc import Callable

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import (
    character,
    encode,
    piece,
    replaced,
    without_prefix,
    without_suffix,
)
from tests.unit.solver.agreement import (
    ALPHABET,
    PATH_LETTERS,
    asked,
    disagrees,
    flipped_path,
    heads_named,
    needs_cvc5,
)

# the bounds a random slice picks from: missing, negative, and past either end of a string of
# up to five characters
BOUNDS: list[int | None] = [None, *range(-7, 8)]


def test_a_negative_index_counts_back_from_the_end() -> None:
    assert character("s", 2) == "(str.at s 2)"
    assert character("s", -1) == "(str.at s (- (str.len s) 1))"


def test_a_slice_clamps_a_start_that_counts_back_past_the_beginning() -> None:
    back = "(- (str.len s) 2)"
    start = f"(ite (< {back} 0) 0 {back})"

    assert piece("s", -2, None) == f"(str.substr s {start} (- (str.len s) {start}))"


def test_a_slice_with_both_bounds_missing_is_the_whole_string() -> None:
    assert piece("s", None, None) == "(str.substr s 0 (- (str.len s) 0))"


def test_a_removed_prefix_or_suffix_reads_a_literal_length_as_a_number() -> None:
    assert without_prefix("s", '"ab"') == (
        '(ite (str.prefixof "ab" s) (str.substr s 2 (- (str.len s) 2)) s)'
    )
    assert without_suffix("s", '"ab"') == (
        '(ite (str.suffixof "ab" s) (str.substr s 0 (- (str.len s) 2)) s)'
    )


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
    return (lambda s: piece(s, start, stop)), value[start:stop]


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
PIECE_HEADS = ["[]", "[:]", "+", "replace", "removeprefix", "removesuffix"]


def _literal(rng: random.Random, longest: int) -> str:
    return repr("".join(rng.choices(PATH_LETTERS, k=rng.randint(0, longest))))


def _piece_of(rng: random.Random) -> tuple[Expression, Expression | None]:
    """One random piece of s, and the long-enough fork an index records before it, if any."""
    head = rng.choice(PIECE_HEADS)
    if head == "[]":
        index = rng.randint(-3, 2)
        measured: Expression = ["len", "s"]
        fork: Expression = [">", measured, index] if index >= 0 else [">=", measured, -index]
        return ["[]", "s", index], fork
    if head == "[:]":
        return ["[:]", "s", rng.choice([None, -2, 0, 1, 3]), rng.choice([None, -1, 2, 4])], None
    if head == "+":
        pair: list[Expression] = ["s", _literal(rng, 2)]
        return ["+", *(pair if rng.random() < 0.5 else pair[::-1])], None
    if head == "replace":
        return ["replace", "s", repr(rng.choice(PATH_LETTERS)), _literal(rng, 2)], None
    return [head, "s", _literal(rng, 2)], None


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some string takes through random compares on pieces, the last one flipped."""
    s = "".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 5)))
    pieces = (_compared(rng) for _ in range(rng.randint(1, 5)))
    return flipped_path(s, pieces, PYTHON_HEADS)


def _compared(rng: random.Random) -> tuple[Expression, Expression | None]:
    """A random piece compared with a literal, and the fork the piece records first, if any."""
    term, long_enough = _piece_of(rng)
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
