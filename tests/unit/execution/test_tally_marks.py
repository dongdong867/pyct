"""A tally keeps a fork that reads a value a formula gave marked ``summary``, and tells its watch
of the marked fork."""

from pyct.core.entry import in_use
from pyct.core.foundation.branch import Branch, Site
from pyct.core.numbers.ints import ConcolicInt
from pyct.execution.tally import Tally
from tests.unit.execution.test_tally import Heard


def test_a_kept_fork_that_reads_a_formula_s_value_is_marked_and_heard_marked() -> None:
    heard = Heard()
    tally = Tally(heard)
    tally.go_live()
    try:
        term = ["%", "n", 4]
        in_use.gave((ConcolicInt.made(1, expression=term, sink=tally),))
        tally.append(Branch([">", term, 3], False, Site("m.py", 6, 7)))
    finally:
        tally.seal()

    [fork] = tally.branches
    assert (fork.site.line, fork.summary) == (6, True)
    assert [each for kind, each in heard.told if kind == "fork"] == [fork]
    assert [each.summary for kind, each in heard.told if isinstance(each, Branch)] == [True]
