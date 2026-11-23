"""While an input that records loss runs is live, an operation pyct has not taught and a `math`
call it does not follow each record their first runs at their site: the values going in and the
answer."""

import contextlib
import math
import sys
from collections.abc import Iterator

from pyct.core.entry import losses, pieces, substitutes
from pyct.core.entry.pieces import MOST_RUNS, MOST_TEXT, MOST_VALUE
from pyct.core.foundation.branch import Changed, GoingIn, LossKind, LossRun, SinkItem, Site
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr


@contextlib.contextmanager
def live(*, recording: bool = True) -> Iterator[list[SinkItem]]:
    """A live input whose sink is the list yielded, its loss runs recorded with ``recording``."""
    sink: list[SinkItem] = []
    pieces.start(sink)
    if recording:
        losses.start(sink)
    try:
        yield sink
    finally:
        losses.forget()
        pieces.forget()


def runs(sink: list[SinkItem]) -> list[LossRun]:
    return [item for item in sink if isinstance(item, LossRun)]


def here() -> int:
    """The line after the one that called this."""
    return sys._getframe(1).f_lineno + 1


def value(text: str, tracked: bool, at: int) -> GoingIn:  # noqa: FBT001
    return GoingIn(f"arg{at}", text, tracked)


def test_an_operation_pyct_has_not_taught_records_its_values_going_in_and_its_answer() -> None:
    with live() as sink:
        n = ConcolicInt.made(13, expression="n", sink=sink)
        line = here()
        k = n >> 2

    assert k == 3
    [run] = runs(sink)
    assert run == LossRun(
        Site(__file__, line, 12),
        "__rshift__",
        LossKind.OPERATION,
        (value("13", True, 1), value("2", False, 2)),
        (Changed("answer", "3"),),
    )


def test_a_reflected_operation_records_its_tracked_receiver_first() -> None:
    with live() as sink:
        n = ConcolicInt.made(2, expression="n", sink=sink)
        _ = 1 << n

    [run] = runs(sink)
    assert run.name == "__rlshift__"
    assert run.going_in == (value("2", True, 1), value("1", False, 2))
    assert run.changed == (Changed("answer", "4"),)


def test_a_method_records_its_arguments_after_its_receiver() -> None:
    with live() as sink:
        s = ConcolicStr.made("a\tb", expression="s", sink=sink)
        _ = s.expandtabs(4)

    [run] = runs(sink)
    assert (run.name, run.going_in) == (
        "expandtabs",
        (value('"a\\tb"', True, 1), value("4", False, 2)),
    )
    assert run.changed == (Changed("answer", '"a   b"'),)


def test_each_site_records_its_first_runs_alone() -> None:
    with live() as sink:
        for each in range(MOST_RUNS + 2):
            _ = ConcolicInt.made(each, expression="n", sink=sink) >> 1

    assert [run.going_in[0].value for run in runs(sink)] == [str(each) for each in range(MOST_RUNS)]


def test_a_second_name_at_a_site_records_nothing_there() -> None:
    with live() as sink:
        n = ConcolicInt.made(5, expression="n", sink=sink)
        for name in ("__rshift__", "__lshift__"):
            _ = getattr(n, name)(1)

    assert [run.name for run in runs(sink)] == ["__rshift__"]


def test_a_value_that_is_not_plain_json_or_too_long_records_no_run() -> None:
    with live() as sink:
        n = ConcolicInt.made(5, expression="n", sink=sink)
        _ = n.to_bytes(2, "big")
        s = ConcolicStr.made("a" * MOST_VALUE, expression="s", sink=sink)
        _ = s.expandtabs()

    assert runs(sink) == []


def test_an_operation_on_a_tracked_list_records_no_run() -> None:
    with live() as sink:
        xs = ConcolicList.made([3, 1], expression="xs", sink=sink)
        _ = xs.copy()

    assert runs(sink) == []


def test_a_math_call_pyct_does_not_follow_records_its_arguments_and_its_answer() -> None:
    gcd = substitutes.call(math.gcd)
    with live() as sink:
        n = ConcolicInt.made(12, expression="n", sink=sink)
        line = here()
        answer = gcd(n, 8)

    assert answer == 4
    [run] = runs(sink)
    assert (run.site.line, run.name, run.kind) == (line, "gcd", LossKind.MATH)
    assert run.going_in == (value("12", True, 1), value("8", False, 2))


def test_with_the_recording_off_nothing_is_recorded() -> None:
    with live(recording=False) as sink:
        n = ConcolicInt.made(13, expression="n", sink=sink)
        _ = n >> 2
        _ = substitutes.call(math.gcd)(n, 8)

    assert runs(sink) == []
    assert len(sink) == 2


def test_the_runs_share_what_the_input_s_recorded_runs_may_count() -> None:
    with live() as sink:
        n = ConcolicInt.made(13, expression="n", sink=sink)
        assert pieces.counted(MOST_TEXT - 10)
        _ = n >> 2

    assert runs(sink) == []


def test_no_input_live_records_nothing() -> None:
    sink: list[SinkItem] = []

    _ = ConcolicInt.made(13, expression="n", sink=sink) >> 2

    assert runs(sink) == []
