"""A split's count where the path asks it: exact where a fork compares it with a plain int,
directly or through plain arithmetic, and c* where it meets anything else; a piece from the end
read where c* puts it, and asked once more where the input's own count puts it; with cvc5 held
against Python on each."""

from typing import Any

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.solver import cvc5 as cvc5_module
from pyct.solver.answer import Answer, Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.declared import Program
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render import fork

LINES: Expression = ["splitlines", "s"]
REST: Expression = ["[:]", LINES, 2, None]


def _many(count: int) -> str:
    return "a\n" * (count - 1) + "x"


@needs_cvc5
@pytest.mark.parametrize("count", [8, 12])
def test_the_last_of_many_lines_past_a_tracked_count_is_flipped(count: int) -> None:
    path = (
        fork([">", ["len", LINES], "n"], taken=True),
        fork([">=", ["len", LINES], 1], taken=True),
        fork(["==", ["[]", LINES, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(count), "n": 0})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the last line is read where the input's own count puts it, and the count that meets n is
    # that count, where a tie to every line ran past the limit or kept the string
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    lines, n = str(args["s"]).splitlines(), args["n"]
    assert isinstance(n, int) and lines[-1] == "end" and len(lines) > n, args


@needs_cvc5
def test_the_last_of_the_rest_of_many_lines_is_flipped() -> None:
    path = (
        fork(["!=", ["len", REST], 0], taken=True),
        fork([">=", ["len", REST], 1], taken=True),
        fork(["==", ["[]", REST, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(12)})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # read where the input's twelve lines put it, through the slice that runs to their end
    assert isinstance(answer, Sat), answer
    lines = str(apply(seed, answer.model).args["s"]).splitlines()
    assert lines[2:] and lines[2:][-1] == "end", lines


@needs_cvc5
@pytest.mark.parametrize(("count", "answered"), [(8, Sat), (3, Unsat)], ids=["eight", "three"])
def test_a_count_a_tracked_int_meets_is_asked_at_the_input_s_own(
    count: int, answered: type[Answer]
) -> None:
    path = (
        fork(["==", ["len", LINES], "n"], taken=True),
        fork(["==", "n", 8], taken=True),
    )
    seed = Seed.of({"s": _many(count), "n": count})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # as origin/v2 asks it: eight lines answer, and three are a miss that says no input with
    # three lines takes the path (follow-the-length-of-a-split's Not in this story)
    assert isinstance(answer, answered), answer
    if isinstance(answer, Sat):
        args = apply(seed, answer.model).args
        assert len(str(args["s"]).splitlines()) == args["n"] == 8, args


@needs_cvc5
@pytest.mark.parametrize("count", [3, 9])
@pytest.mark.parametrize("settled", [False, True], ids=["a clamp", "a settled start"])
def test_a_piece_read_through_a_slice_keeps_the_condition_that_it_is_there(
    count: int, settled: bool
) -> None:
    # the last of the rest, read where the input's count puts it: through the slice, the
    # condition that the string has that many lines was dropped, and an answer of three lines
    # held 'end' at a ninth that Python never reads
    path = (
        *([fork([">=", ["len", LINES], 3], taken=True)] if settled else []),
        fork([">=", ["len", REST], 1], taken=True),
        fork(["==", ["[]", REST, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(count)})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    lines = str(apply(seed, answer.model).args["s"]).splitlines()
    assert lines[2:] and lines[2:][-1] == "end", lines


@needs_cvc5
def test_a_read_held_to_the_input_s_count_is_asked_again_where_its_own_count_puts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = (
        fork([">=", ["len", LINES], 1], taken=True),
        fork(["==", ["[]", LINES, -1], "'end'"], taken=True),
        fork(["==", ["[]", LINES, 3], "'z'"], taken=True),
    )
    seed = Seed.of({"s": "a\nb\nc"})
    held: list[bool] = []
    ask = cvc5_module._ask

    def recorded(written: Program, timeout: float) -> Any:
        held.append(written.fixed)
        return ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", recorded)

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # held to the input's three lines, no fourth is there: unsat; asked again, the third line is
    # read with no count held, as origin/v2 reads it, and the answer has a fourth
    assert held == [True, False], held
    assert isinstance(answer, Sat), answer
    assert str(apply(seed, answer.model).args["s"]).splitlines()[2] == "end"


@needs_cvc5
def test_an_unknown_to_a_read_held_to_the_input_s_count_is_asked_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = (
        fork([">=", ["len", LINES], 1], taken=True),
        fork(["==", ["[]", LINES, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": "a\nb\nc"})
    held: list[bool] = []
    ask = cvc5_module._ask

    def recorded(written: Program, timeout: float) -> Any:
        held.append(written.fixed)
        return (Unknown(), frozenset()) if written.fixed else ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", recorded)

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert held == [True, False], held
    assert isinstance(answer, Sat), answer


# a fork on a split's count through plain arithmetic, the side taken, and whether Python's
# count takes it
ARITHMETIC: dict[str, tuple[Expression, bool]] = {
    "less one": ([">", ["-", ["len", ["split", "s", "','"]], 1], 3], True),
    "doubled": (["==", ["*", ["len", ["split", "s", "','"]], 2], 8], True),
    "doubled first": (["==", ["*", 2, ["len", ["split", "s", "','"]]], 6], True),
    "the number first": (["<", 3, ["len", ["split", "s", "','"]]], True),
    "one more, not taken": ([">=", ["+", ["len", ["split", "s", "','"]], 1], 4], False),
    "a slice's length": ([">", ["len", ["[:]", ["split", "s", "','"], 2, None]], 2], True),
    "a slice's length, stepped back": (
        ["==", ["len", ["[:]", ["split", "s", "','"], None, None, -1]], 2],
        True,
    ),
}


@needs_cvc5
@pytest.mark.parametrize(("expression", "taken"), ARITHMETIC.values(), ids=list(ARITHMETIC))
def test_a_count_through_plain_arithmetic_is_exact(expression: Expression, taken: bool) -> None:
    path = (fork(expression, taken=taken),)
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    parts = str(apply(seed, answer.model).args["s"]).split(",")
    python = eval(  # noqa: S307
        _python(expression), {"parts": parts}
    )
    assert python is taken, (parts, expression)


def _python(part: Expression) -> str:
    """A fork's expression on ``parts`` as Python writes it."""
    if isinstance(part, int):
        return str(part)
    assert isinstance(part, list)
    head, *operands = part
    if head == "len":
        return f"len({_python(operands[0])})"
    if head == "[:]":
        bounds = ":".join("" if bound is None else str(bound) for bound in operands[1:])
        return f"{_python(operands[0])}[{bounds}]"
    if head == "split":
        return "parts"
    return f"({_python(operands[0])} {head} {_python(operands[1])})"


@needs_cvc5
@pytest.mark.parametrize(
    ("window", "read"),
    [([-2, None], 0), ([None, None, -1], 1), ([-3, -1], 1)],
    ids=["the last two", "stepped back", "between two from the end"],
)
def test_a_piece_through_a_slice_from_the_end_is_read_where_c_star_puts_it(
    window: list[int | None], read: int
) -> None:
    parts: Expression = ["[:]", ["split", "s", "','"], *window]
    path = (
        fork([">", ["len", parts], read], taken=True),
        fork(["==", ["[]", parts, read], "'x'"], taken=True),
    )
    seed = Seed.of({"s": "a,b,c"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # a slice stepped back from the end is read by a walk of the reversed string; any other
    # starts where the input's three pieces put it, and the string keeps three
    assert isinstance(answer, Sat), answer
    pieces = str(apply(seed, answer.model).args["s"]).split(",")
    assert pieces[slice(*window)][read] == "x", pieces
    assert len(pieces) == 3 or window == [None, None, -1], pieces


@needs_cvc5
@pytest.mark.parametrize("count", [18, 24])
def test_the_last_piece_of_an_rsplit_past_its_walk_is_read_where_c_star_puts_it(
    count: int,
) -> None:
    parts: Expression = ["rsplit", "s", "','", 20]
    path = (
        fork([">=", ["len", parts], 1], taken=True),
        fork(["==", ["[]", parts, -1], "'end'"], taken=True),
        fork([">", ["len", parts], 10], taken=True),
    )
    seed = Seed.of({"s": ",".join("a" * count)})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # read by a walk of the reversed string, the count was free, and a later flip asking for
    # more than ten pieces beside it ran past the limit; where c* puts it, it answers
    assert isinstance(answer, Sat), answer
    pieces = str(apply(seed, answer.model).args["s"]).rsplit(",", 20)
    assert pieces[-1] == "end" and len(pieces) > 10, pieces
