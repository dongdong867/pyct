"""The steps a path's tracked-key lookups may take: cvc5 writes each distinct call out over every
key the dict may hold, and a program past the steps its limit gives them is `unknown` at once."""

import time

import pytest

from pyct.binding.annotations import check_of
from pyct.binding.bind import Seed
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, Unknown
from pyct.solver.cvc5 import _origin, solve
from pyct.solver.dict_keys import LookupsTooManyError, call_steps
from pyct.solver.render import program
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


def int_lookup(keys: int) -> tuple[Seed, tuple[Branch, ...]]:
    """A tracked int key looked up in an int-keyed dict of ``keys`` keys, and the value under it
    read and flipped: `if n in d: if d[n] > 5:`."""
    check = check_of(dict[int, int])
    assert check is not None
    seed = Seed.of({"n": 1, "d": dict.fromkeys(range(1, keys + 1), 0)}, {"d": check})
    return seed, (fork(["in", "n", "d"]), fork([">", ["[]", "d", "n"], 5]))


@needs_cvc5
def test_an_int_key_lookup_past_its_steps_is_unknown_at_once() -> None:
    # cvc5's time for an int key grows with the square of the keys: 9.7 s into 3,000
    seed, forks = int_lookup(3000)

    started = time.monotonic()
    answer = solve(forks, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unknown) and time.monotonic() - started < 1.0


def test_an_int_key_lookup_inside_its_steps_is_asked() -> None:
    seed, forks = int_lookup(1000)

    program(forks, seed.leaves, _origin(seed.containers(), seed.values, 10.0))


@pytest.mark.parametrize(("names", "asked"), [(29, True), (30, False)])
def test_str_key_lookups_keep_their_steps(names: int, asked: bool) -> None:
    # 29 str keys looked up and read into 3,000 keys at the 10 s default are asked, 30 not
    seed = Seed.of({"prices": {f"k{i}": 0 for i in range(3000)}, "names": ["k0"] * names})
    forks = tuple(
        part
        for at in range(names)
        for part in (
            fork(["in", ["[]", "names", at], "prices"]),
            fork([">", ["[]", "prices", ["[]", "names", at]], 5]),
        )
    )
    origin = _origin(seed.containers(), seed.values, 10.0)

    if asked:
        program(forks, seed.leaves, origin)
    else:
        with pytest.raises(LookupsTooManyError):
            program(forks, seed.leaves, origin)


@pytest.mark.parametrize(
    ("keys", "typed", "steps"),
    [(10, str, 11), (3000, str, 3001), (10, int, 11), (1000, int, 41_750), (3000, int, 375_250)],
)
def test_a_lookup_s_steps_grow_with_its_keys_or_their_square(
    keys: int, typed: type, steps: int
) -> None:
    assert call_steps(keys, typed) == steps
