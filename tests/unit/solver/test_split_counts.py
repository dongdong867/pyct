"""A split's count where the path asks it: exact where a fork compares it with a plain int,
directly or through plain arithmetic, and c* where it meets anything else; a piece from the end
read where c* puts it, and asked once more where the input's own count puts it; with cvc5 held
against Python on each."""

import contextlib
from typing import Any

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core import bound
from pyct.core.branch import Branch, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
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
    [([-2, None], 0), ([None, None, -1], 1), ([-3, -1], 1), ([-3, None], 1), ([-3, None], 2)],
    ids=["the last two", "stepped back", "between two from the end", "second", "third"],
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


def _recorded(target: Any, args: dict[str, Any]) -> list[Branch]:
    """The forks core records running ``target`` on tracked ``args``, as a run records them."""
    sink: list[Any] = []
    tracked = {
        name: (ConcolicStr if isinstance(value, str) else ConcolicInt).made(value, name, sink)
        for name, value in args.items()
    }
    with contextlib.suppress(IndexError):
        target(**tracked)
    return [item for item in sink if isinstance(item, Branch)]


def _length(items: Any) -> Any:
    """``len(items)`` as the target's package calls it, a tracked int on a tracked list."""
    return bound.len(items)


def _sliced_split(s: Any, n: Any) -> int:
    parts = s[1:].split(",")
    if _length(parts) < n and parts[0] == "end":
        return 2
    return 0


def _split_piece_split(s: Any, n: Any) -> int:
    parts = s.split(";")[0].split(",")
    if _length(parts) < n and parts[0] == "end":
        return 2
    return 0


def _sliced_lines(s: Any, n: Any) -> int:
    lines = s[1:].splitlines()
    return 1 if lines[-1] == "end" else 0


def _appended_lines(s: Any, n: Any) -> int:
    lines = s.splitlines()
    lines.append("")
    return 1 if lines[-2] == "end" and _length(lines) > 4 else 0


def _slice_of_a_slice(s: Any, n: Any) -> int:
    return 1 if _length(s.split(",")[1:][1:]) == 2 else 0


def _slice_of_a_reversal(s: Any, n: Any) -> int:
    return 1 if _length(s.split(",")[::-1][1:]) == 2 else 0


def _number_s_text(s: Any, n: Any) -> int:
    parts = (s + str(n)).split(",")
    return 2 if _length(parts) < n and parts[0] == "end" else 0


def _stripped_count(s: Any, n: Any) -> int:
    return 1 if _length(s.strip().split(",")) != n else 0


def _joined_count(s: Any, n: Any) -> int:
    return 1 if _length((s + ",x").split(",")) == n else 0


def _stripped_lines(s: Any, n: Any) -> int:
    return 1 if _length(s.strip().splitlines()) == n else 0


def _inserted(s: Any, n: Any) -> int:
    parts = s.split(",")
    parts.insert(0, "x")
    return 1 if parts[1] == "end" else 0


def _cut_twice(s: Any, n: Any) -> int:
    return 1 if _length(s.split(",")[5:][:-3]) > 0 else 0


# a target and a seed whose last fork, flipped, an answer must take as Python does: a split of
# a string the arguments make, whose count is the one this run produced, worked out from them,
# or, where the solver cannot work it out, Python's own list, as on origin/v2; a count c*
# learns through a list changed as the encoder reads it; a piece of a list changed at a
# position, which is Python's own; and slices of slices
SHAPES: dict[str, tuple[Any, dict[str, Any]]] = {
    "a number's text split": (_number_s_text, {"s": "a,b", "n": 5}),
    "a stripped split's count": (_stripped_count, {"s": "a,b,c\n", "n": 2}),
    "a joined split's count": (_joined_count, {"s": "a", "n": 1}),
    "stripped lines' count": (_stripped_lines, {"s": "a\nb\n", "n": 1}),
    "an inserted split": (_inserted, {"s": "a,b", "n": 0}),
    "a slice of a slice from the end": (_cut_twice, {"s": "a", "n": 0}),
    "a slice's split": (_sliced_split, {"s": "xa,b,c", "n": 4}),
    "a piece's split": (_split_piece_split, {"s": "a,b,c;d", "n": 4}),
    "a slice's lines": (_sliced_lines, {"s": "xa\nb\nc", "n": 0}),
    "an appended line": (_appended_lines, {"s": "end", "n": 0}),
    "a slice of a slice": (_slice_of_a_slice, {"s": "a", "n": 0}),
    "a slice of a reversal": (_slice_of_a_reversal, {"s": "a", "n": 0}),
}


@needs_cvc5
@pytest.mark.parametrize(("target", "args"), SHAPES.values(), ids=list(SHAPES))
def test_a_flipped_count_or_piece_is_taken_as_python_takes_it(
    target: Any, args: dict[str, Any]
) -> None:
    forks = _recorded(target, args)
    seed = Seed.of(args)
    path = (*forks[:-1], fork(forks[-1].expression, taken=not forks[-1].taken))

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the last fork flipped, with every fork before it kept, as Python runs the answer
    assert isinstance(answer, Sat), answer
    new = dict(apply(seed, answer.model).args)
    taken = [(branch.expression, branch.taken) for branch in _recorded(target, new)]
    assert taken[: len(path)] == [(branch.expression, branch.taken) for branch in path], new


@needs_cvc5
def test_a_piece_through_a_slice_held_to_c_star_is_asked_again_at_the_input_s_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parts: Expression = ["split", "s", "','"]
    last: Expression = ["[:]", parts, -2, None]
    path = (
        fork([">", ["len", last], 0], taken=True),
        fork(["==", ["[]", last, 0], "'x'"], taken=True),
        fork(["==", ["[]", parts, 3], "'z'"], taken=True),
    )
    seed = Seed.of({"s": "a,b,c"})
    held: list[bool] = []
    ask = cvc5_module._ask

    def recorded(written: Program, timeout: float) -> Any:
        held.append(written.fixed)
        return ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", recorded)

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # held to the input's three pieces, no fourth is there: unsat; asked again, the slice
    # starts where the input's own three put it, at the second piece, with no count held
    assert held == [True, False], held
    assert isinstance(answer, Sat), answer
    pieces = str(apply(seed, answer.model).args["s"]).split(",")
    assert pieces[1] == "x" and pieces[3] == "z", pieces
