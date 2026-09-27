"""cvc5 held against Python on paths through changed lists.

A random program changes a tracked list the ways a target does, then forks on it. The path it
took, its last fork flipped, goes to the solver as a run asks it. A sat answer is run again in
Python and must take the path the solver was asked for; an unsat answer must have no witness
among the short lists of small ints.
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

# the values a list holds and a fork compares with: few, so a witness search stays small
VALUES = (0, 1, 2)

# one step of a program: what it does, and the plain values it does it with
type Step = tuple[str, tuple[Any, ...]]

# each change a program makes, on the list and the tracked int x, handing back the list the
# program goes on with
CHANGES: dict[str, Callable[..., Any]] = {
    "append": lambda a, x, v: (a.append(v), a)[1],
    "append x": lambda a, x: (a.append(x), a)[1],
    "extend": lambda a, x, v: (a.extend([v, x]), a)[1],
    "insert": lambda a, x, i, v: (a.insert(i, v), a)[1],
    "pop": lambda a, x: (a.pop(), a)[1],
    "pop at": lambda a, x, i: (a.pop(i), a)[1],
    "remove": lambda a, x, v: (a.remove(v), a)[1],
    "set": lambda a, x, i, v: (a.__setitem__(i, v), a)[1],
    "del": lambda a, x, i: (a.__delitem__(i), a)[1],
    "del a slice": lambda a, x, s: (a.__delitem__(s), a)[1],
    "set a slice": lambda a, x, s, v: (a.__setitem__(s, [v]), a)[1],
    "reverse": lambda a, x: (a.reverse(), a)[1],
    "sort": lambda a, x: (a.sort(), a)[1],
    "+": lambda a, x, v: a + [v],
    "radd": lambda a, x, v: [v] + a,
    "*": lambda a, x: a * 2,
    "slice": lambda a, x, s: a[s],
    "reversed": lambda a, x: a[::-1],
    "from x": lambda a, x: a[x:],
}

# each fork a program ends with: a test of the list, tested for truth where the fork is
CHECKS: dict[str, Callable[..., Any]] = {
    "item ==": lambda a, x, i, v: a[i] == v,
    "item >": lambda a, x, i, v: a[i] > v,
    "at x": lambda a, x: a[x] == 1,
    "in": lambda a, x, v: v in a,
    "truth": lambda a, x: bool(a),
    "walk": lambda a, x, v: any(item > v for item in a),
    "==": lambda a, x, v: a == [v, 1],
    "<": lambda a, x, v: a < [v],
}

# how each step draws the plain values it takes
_DRAWS: dict[str, Callable[[random.Random], tuple[Any, ...]]] = {
    "append": lambda r: (r.choice(VALUES),),
    "extend": lambda r: (r.choice(VALUES),),
    "insert": lambda r: (r.randrange(-3, 4), r.choice(VALUES)),
    "pop at": lambda r: (r.randrange(-2, 2),),
    "remove": lambda r: (r.choice(VALUES),),
    "set": lambda r: (r.randrange(-2, 2), r.choice(VALUES)),
    "del": lambda r: (r.randrange(-2, 2),),
    "del a slice": lambda r: (_bounds(r),),
    "set a slice": lambda r: (_bounds(r), r.choice(VALUES)),
    "+": lambda r: (r.choice(VALUES),),
    "radd": lambda r: (r.choice(VALUES),),
    "slice": lambda r: (_bounds(r),),
    "item ==": lambda r: (r.randrange(-3, 3), r.choice(VALUES)),
    "item >": lambda r: (r.randrange(0, 3), r.choice(VALUES)),
    "in": lambda r: (r.choice(VALUES),),
    "walk": lambda r: (r.choice(VALUES),),
    "==": lambda r: (r.choice(VALUES),),
    "<": lambda r: (r.choice(VALUES),),
}


def _bounds(chooser: random.Random) -> slice:
    ends = [None, -2, -1, 0, 1, 2, 3]
    return slice(chooser.choice(ends), chooser.choice(ends))


def program(chooser: random.Random) -> list[Step]:
    """A few changes and then a few forks."""
    changes = [chooser.choice(sorted(CHANGES)) for _ in range(chooser.randrange(0, 4))]
    checks = [chooser.choice(sorted(CHECKS)) for _ in range(chooser.randrange(1, 3))]
    return [(name, _DRAWS.get(name, lambda r: ())(chooser)) for name in changes + checks]


def _run(steps: list[Step], a: Any, x: Any) -> None:
    """The program on the bound list and x: each change, then each check tested for truth."""
    for name, values in steps:
        if name in CHANGES:
            a = CHANGES[name](a, x, *values)
        elif CHECKS[name](a, x, *values):
            continue


def forks(steps: list[Step], args: dict[str, object]) -> tuple[Branch, ...]:
    """The forks a program takes on the arguments, as a run records them, to the first raise."""
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    with contextlib.suppress(IndexError, ValueError, TypeError):
        _run(steps, bound["items"], bound["x"])
    return tuple(item for item in sink if isinstance(item, Branch))


def takes(steps: list[Step], args: dict[str, object], path: tuple[Branch, ...]) -> bool:
    """Whether the arguments take the path: each fork on it, on the side it asks for."""
    taken = forks(steps, args)
    return len(taken) >= len(path) and all(
        mine.taken == wanted.taken for mine, wanted in zip(taken, path, strict=False)
    )


def witness(steps: list[Step], path: tuple[Branch, ...]) -> dict[str, object] | None:
    """Arguments of up to four small ints that take the path, if any do.

    Each seed holds at least one int, so every item the solver may add is an int too: the
    witnesses are the lists it may answer.
    """
    for length in range(5):
        for items in itertools.product(VALUES, repeat=length):
            for x in (-1, 0, 1, 2):
                args: dict[str, object] = {"items": list(items), "x": x}
                if takes(steps, args, path):
                    return args
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
        assert witness(steps, path) is None, (args, path)
        return "unsat"
    return None


@needs_cvc5
@pytest.mark.timeout(300)
def test_cvc5_agrees_with_python_on_paths_through_changed_lists() -> None:
    chooser = random.Random(11)
    answers: list[str | None] = []
    for _ in range(80):
        steps = program(chooser)
        args: dict[str, object] = {
            "items": [chooser.choice(VALUES) for _ in range(chooser.randrange(1, 4))],
            "x": chooser.randrange(-1, 3),
        }
        answers.append(judged(steps, args))
    assert answers.count("sat") >= 30, answers
