from pyct.core.branch import Branch, Downgrade, Site
from pyct.execution.tally import Tally
from pyct.results.record import DowngradeCount

SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", 10], taken=True, site=SITE)


class Heard:
    """A watch that keeps what it was told, in order, as tuples a test can compare."""

    def __init__(self) -> None:
        self.told: list[tuple[object, ...]] = []

    def fork(self, branch: Branch) -> None:
        self.told.append(("fork", branch))

    def line(self, number: int) -> None:
        self.told.append(("line", number))

    def downgrade(self, name: str, count: int) -> None:
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
        tally.append(Downgrade(name=name))

    assert tally.counted() == (
        DowngradeCount(name="__rshift__", count=2),
        DowngradeCount(name="__or__", count=1),
        DowngradeCount(name="__rshift__", count=1),
    )


def test_a_fork_between_two_calls_of_one_name_does_not_split_them() -> None:
    tally = Tally()

    tally.append(Downgrade(name="__abs__"))
    tally.append(FORK)
    tally.append(Downgrade(name="__abs__"))

    # the count runs over the downgrades alone, as the line lists them
    assert tally.counted() == (DowngradeCount(name="__abs__", count=2),)


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
    tally.append(Downgrade(name="__str__"))

    assert tally.branches == [FORK]
    assert tally.counted() == ()


def test_the_watch_hears_each_fact_as_it_happens() -> None:
    heard = Heard()
    tally = Tally(heard)

    tally.line(2)
    tally.append(Downgrade(name="__abs__"))
    tally.append(FORK)
    tally.append(Downgrade(name="__abs__"))
    tally.append(Downgrade(name="__neg__"))

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
    tally.append(Downgrade(name="__str__"))

    assert heard.told == []


def test_a_line_seen_before_is_not_told_again() -> None:
    heard = Heard()
    tally = Tally(heard)

    tally.line(4)
    tally.line(4)

    assert heard.told == [("line", 4)]
