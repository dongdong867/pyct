"""The steps a path's tracked-key lookups may take: cvc5 writes each distinct call out over every
key the dict may hold, and a program past the steps its limit gives them is `unknown` at once."""

import time

from pyct.binding.bind import Seed
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, Unknown
from pyct.solver.cvc5 import solve
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("m.py", 2, 7)


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def lookups(names: int, keys: int) -> tuple[Seed, tuple[Branch, ...]]:
    """A path that looks ``names`` tracked keys up in a dict of ``keys`` keys, each in turn."""
    seed = Seed.of({"prices": {f"k{i}": 0 for i in range(keys)}, "names": ["k0"] * names})
    forks = tuple(fork(["in", ["[]", "names", at], "prices"]) for at in range(names))
    return seed, forks


@needs_cvc5
def test_tracked_key_lookups_past_their_steps_are_unknown_at_once() -> None:
    # cvc5 writes each lookup over every key: 300 into 3,000 keys grew it to 3.8 GB and then
    # ran to the limit; the steps scale with the solve's limit, as a list read's do
    seed, forks = lookups(300, 3000)

    started = time.monotonic()
    answer = solve(forks, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unknown) and time.monotonic() - started < 2.0


@needs_cvc5
def test_tracked_key_lookups_inside_their_steps_are_asked() -> None:
    seed, forks = lookups(5, 100)

    assert isinstance(solve(forks, seed.leaves, 10.0, seed.containers(), seed.values), Sat)


@needs_cvc5
def test_one_tracked_key_looked_up_and_read_in_a_loop_counts_its_steps_once() -> None:
    # `for _ in range(200): if name in prices and prices[name] > 5: ...`: the program writes
    # the same calls on every pass, and cvc5 writes them out once
    seed = Seed.of({"prices": {f"k{i}": 0 for i in range(3000)}, "name": "k5", "x": 0})
    # each pass records lists of its own, as a run's forks do
    passes = [
        part
        for _ in range(200)
        for part in (
            fork(["in", "name", "prices"]),
            fork([">", ["[]", "prices", "name"], 5], taken=False),
        )
    ]

    forks = (*passes, fork([">", "x", 3]))

    answer = solve(forks, seed.leaves, 10.0, seed.containers(), seed.values)
    assert isinstance(answer, Sat), answer
