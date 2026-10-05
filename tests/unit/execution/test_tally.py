import functools
import sys

from pyct.core import escapes
from pyct.core.branch import Branch, Downgrade, Fact, Site
from pyct.core.dicts import ConcolicDict
from pyct.core.lists import ConcolicList
from pyct.execution.tally import Tally
from pyct.results.record import DowngradeCount
from tests.unit.core.test_dict_walk_keys import in_the_target
from tests.unit.core.test_dicts import decided, tracked
from tests.unit.interrupted import Interrupt, at_every_line

# the file the tally's own code comes from, as its frames name it
TALLY = str(sys.modules[Tally.__module__].__file__)
SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", 10], taken=True, site=SITE)


class Heard:
    """A watch that keeps what it was told, in order, as tuples a test can compare."""

    def __init__(self) -> None:
        self.told: list[tuple[object, ...]] = []

    def fork(self, branch: Branch) -> None:
        self.told.append(("fork", branch))

    def fact(self, fact: Fact) -> None:
        self.told.append(("fact", fact))

    def line(self, number: int) -> None:
        self.told.append(("line", number))

    def downgrade(self, name: str, site: Site, count: int) -> None:
        self.told.append(("downgrade", name, count))


def test_a_tally_keeps_the_forks_in_call_order() -> None:
    other = Branch(expression=[">", "y", 0], taken=False, site=SITE)
    tally = Tally()

    tally.append(FORK)
    tally.append(other)

    assert tally.branches == [FORK, other]


def test_a_tally_collapses_consecutive_calls_of_one_name() -> None:
    tally = Tally()

    for name in ("__rshift__", "__rshift__", "__or__", "__rshift__"):
        tally.append(Downgrade(name=name, site=SITE))

    assert tally.counted() == (
        DowngradeCount(name="__rshift__", count=2, site=SITE),
        DowngradeCount(name="__or__", count=1, site=SITE),
        DowngradeCount(name="__rshift__", count=1, site=SITE),
    )


def test_a_tally_keeps_one_name_at_two_sites_apart() -> None:
    other = Site(file="t.py", line=4, col=8)
    tally = Tally()

    tally.append(Downgrade(name="__xor__", site=SITE))
    tally.append(Downgrade(name="__xor__", site=other))
    # an equal site is the same site, whether or not it is the same object
    tally.append(Downgrade(name="__xor__", site=Site(file="t.py", line=4, col=8)))

    assert tally.counted() == (
        DowngradeCount(name="__xor__", count=1, site=SITE),
        DowngradeCount(name="__xor__", count=2, site=other),
    )


def test_the_watch_hears_a_new_entry_for_a_new_site() -> None:
    heard = Heard()
    tally = Tally(heard)
    other = Site(file="t.py", line=4, col=8)

    tally.append(Downgrade(name="__xor__", site=SITE))
    tally.append(Downgrade(name="__xor__", site=other))

    assert heard.told == [("downgrade", "__xor__", 1), ("downgrade", "__xor__", 1)]


def test_a_fork_between_two_calls_of_one_name_does_not_split_them() -> None:
    tally = Tally()

    tally.append(Downgrade(name="__abs__", site=SITE))
    tally.append(FORK)
    tally.append(Downgrade(name="__abs__", site=SITE))

    # the count runs over the downgrades alone, as the line lists them
    assert tally.counted() == (DowngradeCount(name="__abs__", count=2, site=SITE),)


def test_a_tally_keeps_each_line_once() -> None:
    tally = Tally()

    tally.line(4)
    tally.line(5)

    assert tally.lines == {4, 5}


def test_a_sealed_tally_ignores_what_comes_after() -> None:
    tally = Tally()
    tally.append(FORK)
    tally.seal()

    tally.append(FORK)
    tally.append(Downgrade(name="__str__", site=SITE))

    assert tally.branches == [FORK]
    assert tally.counted() == ()


def test_the_watch_hears_each_fact_as_it_happens() -> None:
    heard = Heard()
    tally = Tally(heard)

    tally.line(2)
    tally.append(Downgrade(name="__abs__", site=SITE))
    tally.append(FORK)
    tally.append(Downgrade(name="__abs__", site=SITE))
    tally.append(Downgrade(name="__neg__", site=SITE))

    # a count of 1 starts an entry; a higher count means the last entry grew
    assert heard.told == [
        ("line", 2),
        ("downgrade", "__abs__", 1),
        ("fork", FORK),
        ("downgrade", "__abs__", 2),
        ("downgrade", "__neg__", 1),
    ]


def test_a_sealed_tally_tells_the_watch_nothing() -> None:
    heard = Heard()
    tally = Tally(heard)
    tally.seal()

    tally.append(FORK)
    tally.append(Downgrade(name="__str__", site=SITE))

    assert heard.told == []


def test_a_line_seen_before_is_not_told_again() -> None:
    heard = Heard()
    tally = Tally(heard)

    tally.line(4)
    tally.line(4)

    assert heard.told == [("line", 4)]


def test_an_alarm_between_a_downgrade_s_steps_leaves_the_tally_readable() -> None:
    def trial(interrupt: Interrupt, at: int) -> None:
        tally = Tally()
        interrupt(functools.partial(tally.append, Downgrade(name="__abs__", site=SITE)))
        tally.append(Downgrade(name="__neg__", site=SITE))

        # the interrupted call may be lost, never the entries around it
        assert tally.counted()[-1] == DowngradeCount(name="__neg__", count=1, site=SITE), at

    at_every_line(TALLY, trial)


def test_a_tally_places_each_fact_after_the_forks_before_it_and_tells_the_watch() -> None:
    heard = Heard()
    tally = Tally(heard)
    decided = Fact([">", ["len", "d"], 0], True, SITE)

    tally.append(decided)
    tally.append(FORK)
    tally.append(decided)

    assert tally.branches == [FORK]
    assert tally.facts == [decided, Fact([">", ["len", "d"], 0], True, SITE, after=1)]
    assert heard.told == [("fact", tally.facts[0]), ("fork", FORK), ("fact", tally.facts[1])]


def test_a_fact_from_a_call_that_is_over_names_its_operation_in_the_live_call() -> None:
    over = Tally()
    over.seal()
    live = Tally()
    live.go_live()

    try:
        over.append(Fact(["!=", ["len", "d"], 0], True, SITE, lost_as="__iter__"))
    finally:
        live.seal()

    assert over.facts == [] and live.facts == []
    assert live.counted() == (DowngradeCount(name="__iter__", count=1, site=SITE),)


def test_a_dict_kept_from_a_call_that_is_over_names_each_check_once_in_the_live_call() -> None:
    over = Tally()
    kept = ConcolicDict.made({"a": 1, "b": 2}, "d", over)
    over.seal()
    live = Tally()
    live.go_live()

    try:
        for _ in kept:
            pass
        assert "a" in kept
    finally:
        live.seal()

    # each of the walk's three passes and the lookup, as the forks they were before the facts;
    # a place no check holds names nothing
    assert [(entry.name, entry.count) for entry in live.counted()] == [
        ("__iter__", 3),
        ("__contains__", 1),
    ]


def test_a_list_kept_from_a_call_that_is_over_names_each_decided_check_in_the_live_call() -> None:
    over = Tally()
    kept = ConcolicList.made([1, 2], "items", over)
    list(kept)
    over.seal()
    live = Tally()
    live.go_live()

    try:
        # the earlier call measured it: here the walk's passes and end and the truth test are
        # its decided checks, each named as the operation that took it, never a fact here
        for _ in kept:
            pass
        assert kept
    finally:
        live.seal()

    assert live.facts == [] and live.branches == []
    assert [(entry.name, entry.count) for entry in live.counted()] == [
        ("__iter__", 3),
        ("__bool__", 1),
    ]


def test_a_call_that_goes_live_forgets_the_walk_keys_handed_out_before() -> None:
    # a key an earlier call handed out is no key of this call's path, and is not kept alive
    config, sink = tracked({"a": 1})
    in_the_target("for k in config:\n    pass", config=config)

    Tally().go_live()
    escapes.lost(sink, Downgrade(name="gcd", site=Site("t.py", 1, 0)))

    assert [part for part, _ in decided(sink) if isinstance(part, list)] == []
