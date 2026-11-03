"""cvc5 held against Python on paths through lists that hold floats and bools, flat or in rows.

A random program reads, searches and changes tracked items, then forks on them. The path it took,
its last fork flipped, goes to the solver as a run asks it, with the facts recorded before that
fork. A sat answer is run again in Python and must take the path the solver was asked for. An
unsat answer must have no witness among small lists of the kinds the seed holds at each place, at
any index a program reads by, since an unsat says no input takes the path.

The picks in ``OWN_PLACE`` read a row under its own place, which no term ties to what picked it.
An answer that moves the pick may leave the path, so it is not judged, and an unsat holds for that
row alone (known limit L8). An answer that keeps the pick is judged as any other.
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
from pyct.core.foundation.branch import (
    Branch,
    Downgrade,
    Expression,
    Fact,
    SinkItem,
    as_the_code_read_it,
)
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
    "rows cut i": lambda rows, i: rows[i:][0],
    "rows + rows": lambda rows, i: (rows + rows)[1],
    "row under a key": lambda rows, i: rows[i],
}

# the picks that hand out a row under its own place, which another input's index or length may
# move: an answer that moves them may leave the path on an int, as on origin/v2 (known limit L8)
OWN_PLACE = frozenset({"rows cut i", "rows + rows", "row under a key"})

# the operations that hand out a row's item: on a row under its own place each hands a float or
# a bool out plain, with a downgrade of its name at the read (`core.list_reads.handed`)
HANDING = frozenset(
    {"__getitem__", "__iter__", "__reversed__", "pop", "count", "index", "remove", "__contains__"}
)

# the steps that write a plain value into the list
WRITES = frozenset({"append", "insert", "set", "+"})

# the picks another input's index or length moves: its row may hold another kind
MOVING = tuple(pick for pick in PICKS if pick not in ("row 0", "row under a key"))

# the doubles a witness search over two rows tries, fewer since it tries every row and index
ROW_WITNESS_FLOATS = (0.0, 1.5, 2.5, float("nan"), float("inf"))

type Step = tuple[str, float]

# the fixed seeds a test's programs come from
ROUNDS = (13, 101, 202, 303, 404, 505, 606)

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


# rows under a tracked key: the rows above, and one of ints alone, which the key follows
KEYED_ROWS: tuple[Callable[[random.Random], list[list[object]]], ...] = (
    *ROWS,
    lambda r: [[r.randrange(0, 3)], [r.randrange(0, 3), r.randrange(0, 3)]],
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


def recorded(steps: list[Step], args: dict[str, object]) -> tuple[Branch | Fact | Downgrade, ...]:
    """The forks and facts a program records on the arguments, as a run does, to the first
    raise."""
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    with contextlib.suppress(IndexError, ValueError, TypeError, OverflowError):
        _run(steps, bound)
    return tuple(item for item in sink if isinstance(item, Branch | Fact | Downgrade))


def forks(steps: list[Step], args: dict[str, object]) -> tuple[Branch, ...]:
    """The forks a program takes on the arguments, as a run records them, to the first raise."""
    return tuple(item for item in recorded(steps, args) if isinstance(item, Branch))


def _as_any_kind(expression: Expression) -> Expression:
    """A fork as a run of any item's kind would write it: reads as any read is, and the truth of
    a number as a bare read, since an int's truth is written as a compare with zero."""
    form = as_the_code_read_it(expression)
    if isinstance(form, list) and len(form) == 3 and form[0] == "!=" and form[2] in (0, 0.0):
        return form[1]
    return form


def proves(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether the arguments take the very path, whatever kind each read finds: its forks each
    on the side it asks for. A program's checks share one line, so the fork's expression tells
    them apart."""
    taken, wanted = _past_finite(forks(steps, args)), _past_finite(path)
    return len(taken) >= len(wanted) and all(
        (_as_any_kind(mine.expression), mine.taken) == (_as_any_kind(want.expression), want.taken)
        for mine, want in zip(taken, wanted, strict=False)
    )


def _kinds_of(items: list[object], floats: tuple[float, ...]) -> list[tuple[object, ...]]:
    """What each place of a list may hold in a witness: values of the kind the seed holds there."""
    return [
        floats if type(item) is float else (True, False) if type(item) is bool else tuple(range(4))
        for item in items
    ]


def _shorter(items: list[object], floats: tuple[float, ...]) -> Iterable[list[object]]:
    """Each list of the seed's kinds at their places, and none past them, shortest first."""
    choices = _kinds_of(items, floats)
    for length in range(len(items) + 1):
        yield from map(list, itertools.product(*choices[:length]))


def witness(steps: list[Step], path: tuple[Branch, ...], args: dict[str, Any]) -> object:
    """Arguments of the seed's kinds at their places, and none past them, that take the path: on
    a list of rows, at any index, and with every row varied, but that a program under
    ``OWN_PLACE`` keeps its index, which no term of its path follows."""
    if "i" not in args:
        for items in _shorter(args["items"], WITNESS_FLOATS):
            if proves(steps, {**args, "items": items}, path):
                return items
        return None
    return _row_witness(steps, path, args)


def _row_witness(steps: list[Step], path: tuple[Branch, ...], args: dict[str, Any]) -> object:
    rows: Any = args["items"]
    keys = list(rows) if isinstance(rows, dict) else None
    held = rows.values() if isinstance(rows, dict) else rows
    each = [list(_shorter(row, ROW_WITNESS_FLOATS)) for row in held]
    indexes = [args["i"]] if steps[0][0] in OWN_PLACE else keys or list(range(-2, 2))
    for index in indexes:
        for picked in itertools.product(*each):
            made = dict(zip(keys, picked, strict=True)) if keys else [list(row) for row in picked]
            if proves(steps, {**args, "items": made, "i": index}, path):
                return made, index
    return None


def asked(steps: list[Step], args: dict[str, object]) -> tuple[tuple[Branch, ...], Answer] | None:
    """The program's path with its last fork flipped, and cvc5's answer, None where it forks
    nowhere."""
    items = tuple(item for item in recorded(steps, args) if not isinstance(item, Downgrade))
    ends = [at for at, item in enumerate(items) if isinstance(item, Branch)]
    if not ends:
        return None
    last = items[ends[-1]]
    assert isinstance(last, Branch)
    flipped = Branch(last.expression, not last.taken, last.site)
    prefix = (*items[: ends[-1]], flipped)
    path = tuple(item for item in prefix if isinstance(item, Branch))
    seed = Seed.of(args)
    return path, solve(prefix, seed.leaves, 5.0, {**seed.lists, **seed.dicts}, seed.values)


def judged(steps: list[Step], args: dict[str, object]) -> str | None:
    """How cvc5 answers the program's path with its last fork flipped, once Python agrees:
    sat or unsat, None for any other answer or a program that forks nowhere.

    A sat answer that adds a null to a list of other kinds, which the program may then read and
    raise on, is not judged (known limit O3), nor is one that moves the pick of a row under its
    own place (``OWN_PLACE``). One that reads an item of another kind takes the forks that kind
    takes, so the path is compared past any `isfinite` the path does not hold, and one stopped by
    such a check is not judged (known limit L9); nor is one whose row under its own place hands
    its float out plain, which records no fork (known limit L8)."""
    got = asked(steps, args)
    if got is None:
        return None
    path, answer = got
    if isinstance(answer, Sat):
        solved = apply(Seed.of(args), answer.model).args
        if _nulls(solved) > _nulls(args) or _moved_the_pick(steps, args, solved):
            return None
        if _stopped_by_another_kind(steps, dict(solved), path):
            return None
        assert follows(steps, dict(solved), path), (steps, args, solved, path)
        return "sat"
    if isinstance(answer, Unsat):
        assert witness(steps, path, args) is None, (steps, args, path)
        return "unsat"
    return "error" if isinstance(answer, Error) else None


def follows(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether an answer does what its path asks. It takes the path, past any `isfinite` an item
    of another kind takes. On a row under its own place, a float the target wrote is plain and
    can take or leave forks the path does not hold (L8), so the answer need only reach the
    flipped fork."""
    taken = forks(steps, args)
    if steps[0][0] in OWN_PLACE:
        wanted = (_as_any_kind(path[-1].expression), path[-1].taken)
        return wanted in [(_as_any_kind(fork.expression), fork.taken) for fork in taken]
    return compare(_past_finite(path), _past_finite(taken)) is None


def _stopped_by_another_kind(
    steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]
) -> bool:
    """Whether the answer's run ends before the flipped fork for a reason of another kind's own:
    a float's `isfinite` the path does not hold (L9), or, on a row under its own place, a plain
    float, handed out so by a step's read of the row, with a downgrade of that read at the step's
    line, or written by the target, which no fork records (L8)."""
    made = recorded(steps, args)
    taken = [item for item in made if isinstance(item, Branch)]
    if len(_past_finite(taken)) >= len(_past_finite(path)):
        return False
    if taken and _is_finite_check(taken[-1]) and not taken[-1].taken:
        return not any(_is_finite_check(fork) for fork in path)
    if steps[0][0] not in OWN_PLACE:
        return False
    lines = {{**CHANGES, **ROW_CHECKS}[name].__code__.co_firstlineno for name, _ in steps[1:]}
    handed = any(
        isinstance(item, Downgrade) and item.name in HANDING and item.site.line in lines
        for item in made
    )
    return handed or any(step[0] in WRITES for step in steps)


def _past_finite(path: Iterable[Branch]) -> tuple[Branch, ...]:
    """The forks, without each `isfinite` but the flipped one, which is the fork asked for."""
    forks = tuple(path)
    return tuple(
        fork for at, fork in enumerate(forks) if at == len(forks) - 1 or not _is_finite_check(fork)
    )


def _is_finite_check(fork: Branch) -> bool:
    form = fork.expression
    return isinstance(form, list) and form[0] == "isfinite"


def _moved_the_pick(steps: list[Step], args: Any, solved: Any) -> bool:
    """Whether an answer to a program on a row under its own place reads another row there."""
    if steps[0][0] not in OWN_PLACE:
        return False
    before, after = args["items"], solved["items"]
    kept = before.keys() == after.keys() if isinstance(before, dict) else len(before) == len(after)
    return not kept or args["i"] != solved["i"]


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
            answers.append(judged(program(chooser), {"items": chooser.choice(SEEDS)(chooser)}))
    assert answers.count("sat") >= 210, answers
    assert answers.count("unsat") >= 55, answers


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_a_row_at_a_place() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(60):
            answers.append(judged(row_program(chooser, "row 0"), rows_seed(chooser)))
    assert answers.count("sat") >= 240, answers
    assert answers.count("unsat") >= 80, answers


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_a_row_an_index_picks() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(60):
            steps = row_program(chooser, chooser.choice(MOVING))
            args = rows_seed(chooser)
            answer = judged(steps, args)
            assert answer != "error", (steps, args)
            answers.append(answer)
    assert answers.count("sat") >= 180, answers
    assert answers.count("unsat") >= 25, answers


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_a_row_a_tracked_key_picks() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(30):
            steps = row_program(chooser, "row under a key")
            rows = chooser.choice(KEYED_ROWS)(chooser)
            args: dict[str, object] = {"items": dict(zip("ab", rows, strict=True))}
            args["i"] = chooser.choice("ab")
            answer = judged(steps, args)
            assert answer != "error", (steps, args)
            answers.append(answer)
    assert answers.count("sat") >= 65, answers
    assert answers.count("unsat") >= 8, answers


def keyed_program(chooser: random.Random) -> list[tuple[str, str, int]]:
    """Reads of an int inside a dict of dicts, by a plain or a tracked key at each level."""
    reads = [("a", "b"), ("a", "p"), ("x", "b"), ("y", "b"), ("x", "p"), ("x", "q"), ("y", "q")]
    length = chooser.randrange(1, 4)
    return [(*chooser.choice(reads), chooser.randrange(0, 4)) for _ in range(length)]


def keyed_recorded(steps: list[tuple[str, str, int]], args: dict[str, Any]) -> list[SinkItem]:
    """What a keyed program records on the arguments, to the first raise."""
    sink: list[SinkItem] = []
    bound: Any = bind(args, sink)
    with contextlib.suppress(KeyError, TypeError):
        for outer, inner, number in steps:
            row = bound["d"][bound["a"] if outer == "a" else outer]
            if row[bound["b"] if inner == "b" else inner] == number:
                continue
    return sink


def keyed_witness(
    steps: list[tuple[str, str, int]], args: dict[str, Any], path: tuple[Branch, ...]
) -> object:
    """Arguments of the seed's keys that take the path."""
    values = itertools.product(range(4), repeat=4)
    for a, b, (one, two, three, four) in itertools.product("xy", "pq", values):
        made = {"x": {"p": one, "q": two}, "y": {"p": three, "q": four}}
        candidate = {"d": made, "a": a, "b": b}
        taken = [i for i in keyed_recorded(steps, candidate) if isinstance(i, Branch)]
        if len(taken) >= len(path) and all(
            (mine.expression, mine.taken) == (want.expression, want.taken)
            for mine, want in zip(taken, path, strict=False)
        ):
            return candidate
    return None


def _is_a_compare(expression: object) -> bool:
    return isinstance(expression, list) and expression[0] == "=="


def keyed_sides(steps: list[tuple[str, str, int]], args: dict[str, Any]) -> list[bool]:
    """The side each compare of a keyed program takes in plain Python: the forks of a path name
    a row's lookups once, so another key can record fewer of them and still take every side."""
    return [
        args["d"][args["a"] if outer == "a" else outer][args["b"] if inner == "b" else inner]
        == number
        for outer, inner, number in steps
    ]


def keyed_answer(steps: list[tuple[str, str, int]], args: dict[str, Any]) -> str | None:
    """How cvc5 answers a keyed program's path with its last fork flipped, once Python agrees."""
    items = [i for i in keyed_recorded(steps, args) if isinstance(i, Branch | Fact)]
    ends = [at for at, item in enumerate(items) if isinstance(item, Branch)]
    last = items[ends[-1]]
    assert isinstance(last, Branch)
    prefix = (*items[: ends[-1]], Branch(last.expression, not last.taken, last.site))
    path = tuple(item for item in prefix if isinstance(item, Branch))
    seed = Seed.of(args)
    answer = solve(prefix, seed.leaves, 5.0, {**seed.lists, **seed.dicts}, seed.values)
    assert not isinstance(answer, Error), (steps, args, answer)
    if isinstance(answer, Sat):
        solved = dict(apply(seed, answer.model).args)
        if solved["a"] != args["a"] and any(outer == "a" for outer, _, _ in steps):
            # the row a tracked key picks keeps its own place (known limit L8)
            return None
        wanted = [fork.taken for fork in path if _is_a_compare(fork.expression)]
        assert keyed_sides(steps, solved) == wanted, (steps, args, solved)
        return "sat"
    if isinstance(answer, Unsat):
        assert keyed_witness(steps, args, path) is None, (steps, args, path)
        return "unsat"
    return None


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_ints_a_tracked_key_picks_from_a_dict_of_dicts() -> None:
    answers: list[str | None] = []
    for round_seed in ROUNDS:
        chooser = random.Random(round_seed)
        for _ in range(40):
            rows = {"x": {"p": 1, "q": 5}, "y": {"p": 2, "q": 3}}
            args = {"d": rows, "a": chooser.choice("xy"), "b": chooser.choice("pq")}
            answers.append(keyed_answer(keyed_program(chooser), args))
    assert answers.count("sat") >= 180, answers
    assert answers.count("unsat") >= 8, answers
