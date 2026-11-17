"""A later line of ``splitlines()``, written as fresh pieces glued together: answered within the
limit, and read as Python reads it."""

import random
import time
from collections.abc import Callable

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.foundation.branch import Branch, Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.glued import Glued
from pyct.solver.lists import Origin
from pyct.solver.render import program
from pyct.solver.split_lists import SplitList
from pyct.solver.splits import SPLITS, named_classes
from pyct.solver.strings import encode
from tests.unit.solver.agreement import asked, needs_cvc5
from tests.unit.solver.test_render import fork

# every line break splitlines knows, "\r\n" among them
LINE_BREAKS = [
    "\n",
    "\r",
    "\r\n",
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    "\u2028",
    "\u2029",
]

# strings whose lines are worth a look: a trailing break, a blank line, a carriage return before
# a line feed and apart from one, and the empty string
LINE_CASES = [
    "",
    "a",
    "\n",
    "a\n",
    "a\n\nb",
    "\r\n",
    "\r\r\n",
    "\n\r",
    "a\r\nb\rc",
    "\r\n\r",
    "a\n\n",
]


def _seeded(s: str) -> Seed:
    return Seed.of({"s": s})


def _line(lines: Expression, at: int) -> Expression:
    return ["[]", lines, at]


def _searched(lines: Expression, last: int) -> list[Branch]:
    """The forks `"END" in lines` records up to line ``last``, which is flipped to "END"."""
    return [fork(["==", _line(lines, at), "'END'"], taken=at == last) for at in range(last + 1)]


def _looped(lines: Expression, count: int) -> list[Branch]:
    """found_beside_a_loop's path over ``count`` lines of "a", its loop's last fork flipped to
    "x": no line is "END", and no line before the last is "x" or "y"."""
    path = [fork(["==", _line(lines, at), "'END'"], taken=False) for at in range(count)]
    for at in range(count - 1):
        path += [fork(["==", _line(lines, at), literal], taken=False) for literal in ("'x'", "'y'")]
    return [*path, fork(["==", _line(lines, count - 1), "'x'"], taken=True)]


@needs_cvc5
@pytest.mark.parametrize(
    ("make", "wanted"),
    [(lambda lines: _searched(lines, 19), "END"), (lambda lines: _looped(lines, 20), "x")],
    ids=["the search's line 19", "the loop's line 19"],
)
def test_a_later_line_is_answered_within_a_second(
    make: Callable[[Expression], list[Branch]], wanted: str
) -> None:
    lines: Expression = ["splitlines", "s"]
    path = tuple(make(lines))
    seed = _seeded("\n".join(["a"] * 20))

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)
    elapsed = time.perf_counter() - started

    assert isinstance(answer, Sat), answer
    assert elapsed < 1.0, elapsed
    found = str(apply(seed, answer.model).args["s"]).splitlines()
    assert found[19] == wanted and "END" not in found[:19], found


def _two_calls(at: int) -> tuple[Branch, ...]:
    """Line ``at`` read on one call of splitlines, then the same line flipped on another."""
    one: Expression = ["splitlines", "s"]
    two: Expression = ["splitlines", "s"]
    return fork(["==", _line(one, at), "'a'"], taken=True), fork(
        ["==", _line(two, at), "'a'"], taken=False
    )


def _line_beside_a_count() -> tuple[Branch, ...]:
    """Line 2 read on one call of splitlines, beside a count of 2 on another."""
    one: Expression = ["splitlines", "s"]
    two: Expression = ["splitlines", "s"]
    return fork(["==", _line(one, 2), "'a'"], taken=True), fork(["==", ["len", two], 2], taken=True)


@needs_cvc5
@pytest.mark.parametrize(
    "path",
    [_two_calls(1), _two_calls(2), _two_calls(5), _line_beside_a_count()],
    ids=["line 1 twice", "line 2 twice", "line 5 twice", "a line beside a count"],
)
def test_two_calls_on_one_string_answer_an_unsat_at_once(path: tuple[Branch, ...]) -> None:
    # each call's lines are the string's, so the second contradicts the first
    seed = _seeded("\n".join(["a"] * 20))

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)
    elapsed = time.perf_counter() - started

    assert isinstance(answer, Unsat), answer
    assert elapsed < 1.0, elapsed


def _reads(value: str, head: str, operands: tuple[object, ...]) -> tuple[list[str], list[object]]:
    """A program that reads each piece of ``value`` and the two past them, and whether each is
    there, as the glued pieces read them, and what Python says of each. One program a value:
    cvc5 answers each in hundredths of a second, and a hundred strings in one ran past a
    minute."""
    declared: list[str] = []
    listed = SplitList("s", head, operands, "count!0!", walked=0, glued=Glued("s", declared))
    pieces = getattr(value, head)(*operands)
    cases: list[tuple[str, str]] = []
    python: list[object] = []
    for index in range(len(pieces) + 2):
        read = listed.at(index)
        assert read.value is not None
        cases.append(("Bool", read.guard))
        python.append(index < len(pieces))
        if index < len(pieces):
            cases.append(("String", read.value))
            python.append(pieces[index])
    lines = ["(set-logic ALL)", "(declare-const s String)", f"(assert (= s {encode(value)}))"]
    lines += declared
    lines += [f"(define-fun v{at} () {sort} {term})" for at, (sort, term) in enumerate(cases)]
    lines[1:1] = named_classes("\n".join(lines))
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]
    return lines, python


def _disagreements(values: list[str], head: str, operands: tuple[object, ...]) -> list[str]:
    """The values whose pieces cvc5 reads otherwise than Python."""
    wrong = []
    for value in values:
        lines, python = _reads(value, head, operands)
        if asked(lines) != python:
            wrong.append(value)
    return wrong


def _line_values() -> list[str]:
    """The strings the lines are read on: the cases above, each break alone, between letters and
    at the end, and random strings of letters and breaks."""
    rng = random.Random(7)
    values = list(LINE_CASES)
    values += [f"a{brk}b{brk}" for brk in LINE_BREAKS] + [f"{brk}{brk}a" for brk in LINE_BREAKS]
    values += [
        "".join(rng.choices(["a", " ", *LINE_BREAKS], k=rng.randint(0, 6))) for _ in range(20)
    ]
    return values


@needs_cvc5
@pytest.mark.parametrize("operands", [(), (True,)], ids=["ends left", "ends kept"])
def test_cvc5_reads_each_line_as_python_does(operands: tuple[object, ...]) -> None:
    assert _disagreements(_line_values(), "splitlines", operands) == []


@needs_cvc5
def test_a_line_past_the_string_s_lines_may_be_missing_or_there() -> None:
    lines: Expression = ["splitlines", "s"]
    seed = _seeded("a\nb\nc")
    # the target reads line 19 only where it is there
    there = fork([">", ["len", lines], 19], taken=True)
    path = (there, fork(["==", _line(lines, 19), "'END'"], taken=True))

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert str(apply(seed, answer.model).args["s"]).splitlines()[19] == "END"
    # line 19 asked missing beside the glued pieces it is read from: they rule out no string
    declared: list[str] = []
    listed = SplitList("s0", "splitlines", (), "count!0!", walked=19, glued=Glued("s0", declared))
    missing = f"(not {listed.past(19)})"
    text = [
        "(set-logic ALL)",
        "(declare-const s0 String)",
        *declared,
        f"(assert {missing})",
        "(declare-const v0 String)",
        "(assert (= v0 s0))",
        "(assert (> (str.len s0) 3))",
        "(check-sat)",
        "(get-value (v0))",
    ]
    text[1:1] = named_classes("\n".join(text))
    (value,) = asked(text)
    assert isinstance(value, str) and len(value) > 3 and len(value.splitlines()) < 20, value


def test_a_count_or_a_read_from_the_end_is_written_as_before() -> None:
    lines: Expression = ["splitlines", "s"]
    counted = (fork(["==", ["len", lines], 4], taken=True),)
    from_the_end = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'end'"], taken=True),
    )
    origin = Origin(values={"s": "a\nb"})

    for path in (counted, from_the_end):
        text = program(path, {"s": str}, origin).text
        # by the walk, as before: no piece is declared
        assert "piece!" not in text and "left!" not in text, text
    count_text = program(counted, {"s": str}, origin).text
    assert SPLITS["splitlines"]("|arg.s|", (), 3)[1] in count_text
