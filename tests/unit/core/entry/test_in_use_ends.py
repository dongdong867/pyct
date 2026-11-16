"""How a run of a loop in use ends: a run still open when an inner frame dropped its formula
calls it no more."""

from collections.abc import Mapping

from pyct.core.entry.in_use import LoopInUse
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
