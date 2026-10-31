"""cvc5 held against Python on paths through lists and dicts that hold floats and bools.

A random program reads, searches and changes tracked items, then forks on them. The path it took,
its last fork flipped, goes to the solver as a run asks it. A sat answer is run again in Python and
must take the path the solver was asked for; an unsat answer must have no witness among small
lists of the kinds the seed holds.
"""

import contextlib
import itertools
import random
from collections.abc import Callable
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.core.branch import Branch, SinkItem
from pyct.solver.answer import Sat, Unsat
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

# the steps that read from the end of the list
FROM_THE_END = frozenset({"last <", "pop", "reversed"})

type Step = tuple[str, float]

# the items each seed starts from: floats, floats and bools, ints beside a float, and all three
SEEDS: tuple[Callable[[random.Random], list[object]], ...] = (
    lambda r: [r.choice(FLOATS) for _ in range(r.randrange(1, 4))],
    lambda r: [r.choice(FLOATS), r.choice((True, False))],
    lambda r: [r.randrange(0, 3), r.choice(FLOATS)],
    lambda r: [r.choice(FLOATS), r.randrange(0, 3), r.choice((True, False))],
)


def program(chooser: random.Random) -> list[Step]:
    """A few changes and then a few forks."""
    names = [chooser.choice(sorted(CHANGES)) for _ in range(chooser.randrange(0, 3))]
    names += [chooser.choice(sorted(CHECKS)) for _ in range(chooser.randrange(1, 3))]
    return [(name, chooser.choice(FLOATS)) for name in names]


def _run(steps: list[Step], items: Any) -> None:
    for name, value in steps:
        if name in CHANGES:
            items = CHANGES[name](items, value)
        elif CHECKS[name](items, value):
            continue


def forks(steps: list[Step], args: dict[str, object]) -> tuple[Branch, ...]:
    """The forks a program takes on the arguments, as a run records them, to the first raise."""
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    with contextlib.suppress(IndexError, ValueError, TypeError):
        _run(steps, bound["items"])
    return tuple(item for item in sink if isinstance(item, Branch))


def takes(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether the arguments take the path: each fork on it, on the side it asks for."""
    taken = forks(steps, args)
    return len(taken) >= len(path) and all(
        mine.taken == wanted.taken for mine, wanted in zip(taken, path, strict=False)
    )


def witness(steps: list[Step], path: tuple[Branch, ...], seed: list[object]) -> object:
    """Items of the seed's kinds at their positions, and none past them, that take the path.

    A read from the end of a list of other kinds is typed by the input's kind there, which holds
    the list at the input's length, so only a list of that length is a witness for one.
    """
    choices = [
        WITNESS_FLOATS if type(item) is float else (True, False) if type(item) is bool else range(4)
        for item in seed
    ]
    mixed = len({type(item) for item in seed}) > 1
    reads_the_end = any(name in FROM_THE_END for name, _ in steps)
    shortest = len(seed) if mixed and reads_the_end else 0
    for length in range(shortest, len(seed) + 1):
        for items in itertools.product(*choices[:length]):
            if takes(steps, {"items": list(items)}, path):
                return items
    return None


def judged(steps: list[Step], args: dict[str, object]) -> str | None:
    """How cvc5 answers the program's path with its last fork flipped, once Python agrees:
    sat or unsat, None for any other answer or a program that forks nowhere."""
    taken = forks(steps, args)
    if not taken:
        return None
    last = taken[-1]
    path = (*taken[:-1], Branch(last.expression, not last.taken, last.site))
    seed = Seed.of(args)
    answer = solve(path, seed.leaves, 5.0, seed.lists)
    if isinstance(answer, Sat):
        solved = apply(seed, answer.model).args
        assert takes(steps, dict(solved), path), (args, solved, path)
        return "sat"
    if isinstance(answer, Unsat):
        items = args["items"]
        assert isinstance(items, list)
        assert witness(steps, path, items) is None, (args, path)
        return "unsat"
    return None


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_paths_through_floats_and_bools() -> None:
    chooser = random.Random(13)
    answers: list[str | None] = []
    for _ in range(60):
        steps = program(chooser)
        args: dict[str, object] = {"items": chooser.choice(SEEDS)(chooser)}
        answers.append(judged(steps, args))
    assert answers.count("sat") >= 20, answers
    assert answers.count("unsat") >= 3, answers
