"""A tally keeps a fork that reads a value a loop's formula gave marked ``summary``, and tells its
watch of the marked fork."""

from pyct.core.entry import in_use, pieces
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch
from pyct.execution.tally import Tally
from tests.unit.core.entry.test_in_use import COUNTS, LOOP, counted, tracked
from tests.unit.core.entry.test_pieces import FILE, hooked
from tests.unit.execution.test_tally import Heard


def test_a_kept_fork_that_reads_a_formula_s_value_is_marked_and_heard_marked() -> None:
    f = hooked(COUNTS)
    heard = Heard()
    tally = Tally(heard)
    in_use.IN_USE[(FILE, *LOOP)] = LoopInUse(("s", "t"), ("t",), counted)
    pieces.start(tally, alone=True)
    try:
        f(tracked("azbz", "s", tally))  # type: ignore[arg-type]
    finally:
        pieces.forget()
        in_use.IN_USE.clear()

    [fork] = tally.branches
    assert (fork.site.line, fork.summary) == (6, True)
    assert [each for kind, each in heard.told if kind == "fork"] == [fork]
    assert [each.summary for kind, each in heard.told if isinstance(each, Branch)] == [True]
