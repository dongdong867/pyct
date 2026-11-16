"""How a run of a loop in use ends: a run still open when an inner frame dropped its formula
calls it no more, and a name the loop changes keeps the loop's value whatever object holds it."""

from collections.abc import Mapping

from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.core.entry.test_in_use import LOOP, RECURSIVE, counted, drops, tracked, using
from tests.unit.core.entry.test_pieces import hooked


def test_a_run_open_in_an_outer_frame_does_not_call_a_formula_an_inner_frame_dropped() -> None:
    calls: list[Mapping[str, object]] = []

    def wrong_at_first(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return {"t": 99} if len(calls) == 1 else counted(values)

    f = hooked(RECURSIVE)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), wrong_at_first)}) as sink:
        t = f(tracked("zz", "s", sink), 1)

    # the first inner call drops it; the outer run's end leaves the loop's own value
    assert len(calls) == 1
    assert len(drops(sink)) == 1
    assert (type(t), t) == (int, 2)


CHANGED = """\
def f(s, n):
    t = 0
    for c in s:
        if c == "z":
            n = n - n + 5
            t += 1
    if n > 3:
        return t, n
    return t, n
"""


def test_a_changed_name_keeps_the_loop_s_value_when_it_is_the_object_the_start_wrote() -> None:
    f = hooked(CHANGED)

    with using({LOOP: LoopInUse(("n", "s", "t"), ("n", "t"), lambda _: {"t": 9, "n": 5})}) as sink:
        result = f(tracked("az", "s", sink), ConcolicInt.made(5, expression="n", sink=sink))

    assert isinstance(result, tuple)
    _, n = result
    # the loop set n to 5, the object the start wrote; the formula was dropped on t
    assert len(drops(sink)) == 1
    assert type(n) is int
    assert [each.expression for each in sink if type(each) is Branch] == []
