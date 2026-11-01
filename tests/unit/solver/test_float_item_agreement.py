"""cvc5 held against Python on paths through lists that hold floats and bools, flat or in rows.

A random program reads, searches and changes tracked items, then forks on them. The path it took,
its last fork flipped, goes to the solver as a run asks it, with the facts recorded before that
fork. A sat answer is run again in Python and must take the path the solver was asked for; an
unsat answer must have no witness among small lists of the kinds the seed holds.

A float or a bool handed out under its own place holds what put it there: an index, a cut's
start, a list's length. On rows an index picks, the witness search varies the picked row at its
own length and keeps the index, since the solver was asked with those held.
"""

import contextlib
import itertools
import math
import random
from collections.abc import Callable, Iterable
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.branches.compare import compare
from pyct.core.branch import Branch, Fact, SinkItem
from pyct.solver.answer import Answer, Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from tests.unit.solver.agreement import needs_cvc5

# the doubles a list holds and a fork compares with: few, so a witness search stays small
FLOATS = (0.0, 0.5, 1.5, 2.5)
WITNESS_FLOATS = (*FLOATS, float("nan"), float("inf"), -1.0)

# each change a program makes, on the list, handing back the list the program goes on with
CHANGES: dict[str, Callable[..., Any]] = {
    "append": lambda a, v: (a.append(v), a)[1],
    "pop": lambda a, v: (a.pop(), a)[1],
    "+": lambda a, v: a + [v],
    "slice": lambda a, v: a[1:],
    "reversed": lambda a, v: a[::-1],
    "set": lambda a, v: (a.__setitem__(0, v), a)[1],
    "sort": lambda a, v: (a.sort(), a)[1],
}

# each fork a program ends with: a test of the list, tested for truth where the fork is
CHECKS: dict[str, Callable[..., Any]] = {
    "item ==": lambda a, v: a[0] == v,
    "item >": lambda a, v: a[0] > v,
    "last <": lambda a, v: a[-1] < v,
    "in": lambda a, v: v in a,
    "count": lambda a, v: a.count(v) == 1,
    "sum": lambda a, v: sum(a) > v,
    "min": lambda a, v: min(a) < v,
    "max": lambda a, v: max(a) > v,
    "same": lambda a, v: a[0] != a[0],
    "add": lambda a, v: a[0] + v > 2.5,
    "truth": lambda a, v: a[0],
}

# the checks of a program on a row: floor is a head render holds for a float and not for an int
ROW_CHECKS = {**CHECKS, "floor": lambda a, v: math.floor(a[0]) == 1}

# how a program reaches its list in a list of rows, by the tracked index ``i``
PICKS: dict[str, Callable[..., Any]] = {
    "row 0": lambda rows, i: rows[0],
    "row i": lambda rows, i: rows[i],
    "row -1": lambda rows, i: rows[-1],
    "row i +": lambda rows, i: rows[i] + [1.5],
    "row -1 cut": lambda rows, i: rows[-1][0:],
    "row 1 cut i": lambda rows, i: rows[1][i:],
    "rows joined": lambda rows, i: rows[0] + rows[1],
}

# the picks the solver cannot place: another input's row may hold another kind
UNPLACED = tuple(pick for pick in PICKS if pick != "row 0")

# the steps that read from the end of the list
FROM_THE_END = frozenset({"last <", "pop", "reversed"})

type Step = tuple[str, float]

# the fixed seeds a test's programs come from
ROUNDS = (13, 101, 202, 303, 404)

# the items each seed starts from: floats, floats and bools, ints beside a float, and all three
SEEDS: tuple[Callable[[random.Random], list[object]], ...] = (
    lambda r: [r.choice(FLOATS) for _ in range(r.randrange(1, 4))],
    lambda r: [r.choice(FLOATS), r.choice((True, False))],
    lambda r: [r.randrange(0, 3), r.choice(FLOATS)],
    lambda r: [r.choice(FLOATS), r.randrange(0, 3), r.choice((True, False))],
)


# rows of one kind, a float's and an int's, and each with a bool
ROWS: tuple[Callable[[random.Random], list[list[object]]], ...] = (
    lambda r: [[r.choice(FLOATS)], [r.choice(FLOATS)]],
    lambda r: [[r.choice((True, False))], [r.choice((True, False)), r.choice((True, False))]],
    lambda r: [[r.choice(FLOATS)], [r.randrange(0, 3)]],
    lambda r: [[r.randrange(0, 3)], [r.choice((True, False))]],
    lambda r: [[r.choice((True, False)), r.choice(FLOATS)], [r.choice(FLOATS), r.randrange(0, 3)]],
)


def program(chooser: random.Random, checks: Iterable[str] = CHECKS) -> list[Step]:
    """A few changes and then a few forks."""
    names = [chooser.choice(sorted(CHANGES)) for _ in range(chooser.randrange(0, 3))]
    names += [chooser.choice(sorted(checks)) for _ in range(chooser.randrange(1, 3))]
    return [(name, chooser.choice(FLOATS)) for name in names]


def row_program(chooser: random.Random, pick: str) -> list[Step]:
    """A program on the row ``pick`` reaches."""
    return [(pick, 0.0), *program(chooser, ROW_CHECKS)]


def _run(steps: list[Step], bound: Any) -> None:
    items = bound["items"]
    for name, value in steps:
        if name in PICKS:
            items = PICKS[name](items, bound["i"])
        elif name in CHANGES:
            items = CHANGES[name](items, value)
        elif ROW_CHECKS[name](items, value):
            continue


def recorded(steps: list[Step], args: dict[str, object]) -> tuple[Branch | Fact, ...]:
    """The forks and facts a program records on the arguments, as a run does, to the first
    raise."""
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    with contextlib.suppress(IndexError, ValueError, TypeError, OverflowError):
        _run(steps, bound)
    return tuple(item for item in sink if isinstance(item, Branch | Fact))


def forks(steps: list[Step], args: dict[str, object]) -> tuple[Branch, ...]:
    """The forks a program takes on the arguments, as a run records them, to the first raise."""
    return tuple(item for item in recorded(steps, args) if isinstance(item, Branch))


def takes(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether the arguments follow the path, by the rule a run's answers are held to."""
    return compare(path, forks(steps, args)) is None


def proves(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether the arguments take the very path: its forks each on the side it asks for. A
    program's checks share one line, so the fork's expression tells them apart."""
    taken = forks(steps, args)
    return len(taken) >= len(path) and all(
        (mine.expression, mine.taken) == (wanted.expression, wanted.taken)
        for mine, wanted in zip(taken, path, strict=False)
    )


def left_out(steps: list[Step], seed: list[object]) -> bool:
    """Whether a program's sat answer may leave its path for a reason named elsewhere: a plain
    float left to Python beside another kind (known limit N5), or a float the target added to
    ints or bools, which a longer input reads at another step and the run reports as leaving
    the plan."""
    names = {name for name, _ in steps}
    kinds = {type(item) for item in seed}
    adds = bool(names & {"append", "+", "set", "row i +"})
    plain_compare = adds and kinds != {float} and bool(names & {"min", "max"})
    return plain_compare or (adds and bool(kinds) and kinds <= {int, bool})


def varied(steps: list[Step], args: dict[str, Any]) -> int | None:
    """The row a witness varies on a list of rows, None on a flat list: row 0 for a program on
    row 0, and else the row the program picks, or reads last."""
    if "i" not in args:
        return None
    rows, pick = args["items"], steps[0][0]
    if pick == "row 0":
        return 0
    if pick in ("row i", "row i +") and -len(rows) <= args["i"] < len(rows):
        return args["i"] % len(rows)
    return len(rows) - 1


def sorted_mixed_row(steps: list[Step], args: dict[str, Any]) -> bool:
    """Whether a program sorts a row an index picks from rows of other kinds: the sorted list is a
    display that names each item by its place in the row, which the solver types by every row's
    kinds, so an unsat may have a witness (known limit L8)."""
    kinds = {type(item) for row in args["items"] for item in row}
    return any(name == "sort" for name, _ in steps) and len(kinds) > 1


def witness(steps: list[Step], path: tuple[Branch, ...], args: dict[str, Any]) -> object:
    """Arguments of the seed's kinds at their places, and none past them, that take the path.

    A read from the end of a list of other kinds is typed by the input's kind there, which holds
    the list at the input's length, so only a list of that length is a witness for one. On a
    list of rows, only the row ``varied`` names is varied, and a row an index picks only at its
    own length, which the path holds with the index.
    """
    row = varied(steps, args)
    seed = args["items"] if row is None else args["items"][row]
    choices = [
        WITNESS_FLOATS if type(item) is float else (True, False) if type(item) is bool else range(4)
        for item in seed
    ]
    mixed = len({type(item) for item in seed}) > 1
    reads_the_end = any(name in FROM_THE_END for name, _ in steps)
    held = row is not None and steps[0][0] != "row 0"
    shortest = len(seed) if (mixed and reads_the_end) or held else 0
    for length in range(shortest, len(seed) + 1):
        for items in itertools.product(*choices[:length]):
            if proves(steps, {**args, "items": _with(args["items"], row, list(items))}, path):
                return items
    return None


def _with(items: list[Any], row: int | None, values: list[object]) -> list[Any]:
    """The list of the seed with ``values`` in place of row ``row``, or in place of the list."""
    if row is None:
        return values
    return [values if at == row else list(each) for at, each in enumerate(items)]


def asked(steps: list[Step], args: dict[str, object]) -> tuple[tuple[Branch, ...], Answer] | None:
    """The program's path with its last fork flipped, and cvc5's answer, None where it forks
    nowhere."""
    items = recorded(steps, args)
    ends = [at for at, item in enumerate(items) if isinstance(item, Branch)]
    if not ends:
        return None
    last = items[ends[-1]]
    assert isinstance(last, Branch)
    flipped = Branch(last.expression, not last.taken, last.site)
    prefix = (*items[: ends[-1]], flipped)
    path = tuple(item for item in prefix if isinstance(item, Branch))
    seed = Seed.of(args)
    return path, solve(prefix, seed.leaves, 5.0, seed.lists)


def judged(steps: list[Step], args: dict[str, object]) -> str | None:
    """How cvc5 answers the program's path with its last fork flipped, once Python agrees:
    sat or unsat, None for any other answer or a program that forks nowhere.

    A sat answer that adds a null to a list of other kinds, which the program may then read and
    raise on, is not judged (known limit O3)."""
    got = asked(steps, args)
    if got is None:
        return None
    path, answer = got
    if isinstance(answer, Sat):
        solved = apply(Seed.of(args), answer.model).args
        if _nulls(solved) > _nulls(args):
            return None
        assert takes(steps, dict(solved), path), (steps, args, solved, path)
        return "sat"
    if isinstance(answer, Unsat):
        assert witness(steps, path, args) is None, (steps, args, path)
        return "unsat"
    return None


def _nulls(args: Any) -> int:
    """How many nulls the arguments' lists hold, at any depth."""
    if isinstance(args, dict | list):
        values = args.values() if isinstance(args, dict) else args
        return sum(_nulls(value) for value in values)
    return int(args is None)


def rows_seed(chooser: random.Random) -> dict[str, Any]:
    """A list of two rows, and an index of it."""
    return {"items": chooser.choice(ROWS)(chooser), "i": chooser.randrange(-2, 2)}


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_paths_through_floats_and_bools() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(60):
            steps = program(chooser)
            items = chooser.choice(SEEDS)(chooser)
            if not left_out(steps, items):
                answers.append(judged(steps, {"items": items}))
    assert answers.count("sat") >= 100, answers
    assert answers.count("unsat") >= 30, answers


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_a_row_at_a_place() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(60):
            steps = row_program(chooser, "row 0")
            args = rows_seed(chooser)
            if not left_out(steps, args["items"][0]):
                answers.append(judged(steps, args))
    assert answers.count("sat") >= 100, answers
    assert answers.count("unsat") >= 30, answers


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_a_row_an_index_picks() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(60):
            steps = row_program(chooser, chooser.choice(UNPLACED))
            args = rows_seed(chooser)
            got = asked(steps, args)
            assert got is None or not isinstance(got[1], Error), (steps, args, got)
            row = args["items"][varied(steps, args) or 0]
            if not left_out(steps, row) and not sorted_mixed_row(steps, args):
                answers.append(judged(steps, args))
    assert answers.count("sat") >= 100, answers
    assert answers.count("unsat") >= 20, answers
