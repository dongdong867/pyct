"""A loss site in use: each time it runs in a live input that runs alone, its formula runs on the
values going in, at the site, and on a match of their JSON texts the target gets the real answer
tracked with the formula's term, with no downgrade. A mismatch, a raise or a missing answer drops
the formula for the rest of the input, and the input carries the drop after the run it failed on.
Here at an operation pyct has not taught, through foundation's slot, with formulas set by hand."""

import contextlib
import enum
import inspect
from collections.abc import Callable, Iterator, Mapping

from pyct.core.entry import calls_in_use, in_use, losses, pieces
from pyct.core.entry.in_use import CALLS_IN_USE, CallInUse
from pyct.core.entry.recorded import MOST_RUNS
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import (
    Branch,
    Downgrade,
    DropReason,
    Fact,
    FormulaDrop,
    LossRun,
    SinkItem,
    Site,
)
from pyct.core.numbers.ints import ConcolicInt

type Formula = Callable[[Mapping[str, object]], Mapping[str, object]]


def quarter(n: int) -> int:
    return n >> 2


# the site of `n >> 2` in `quarter`
QUARTER = Site(__file__, inspect.getsourcelines(quarter)[1] + 1, 11)


class Marking(list[SinkItem]):
    """A sink that marks each fork as the tally does, as it comes."""

    def append(self, item: SinkItem, /) -> None:
        super().append(in_use.summed(item) if type(item) is Branch else item)


def by_four(values: Mapping[str, object]) -> Mapping[str, object]:
    n = values["n"]
    assert isinstance(n, int)
    return {"answer": n // 4}


def capped(values: Mapping[str, object]) -> Mapping[str, object]:
    n = values["n"]
    assert isinstance(n, int)
    q = n // 4
    if q > 9:
        q = 9
    return {"answer": q}


def squared(values: Mapping[str, object]) -> Mapping[str, object]:
    n = values["n"]
    assert isinstance(n, int)
    return {"answer": n * n}


@contextlib.contextmanager
def using(formula: Formula, *, alone: bool = True, recording: bool = True) -> Iterator[Marking]:
    """A live input, the site of `quarter`'s shift in use with ``formula``, whose sink is the
    list yielded, in a call that runs alone unless ``alone`` is False, its loss runs recorded
    with ``recording``."""
    CALLS_IN_USE[(QUARTER.file, QUARTER.line, QUARTER.col)] = CallInUse(
        "__rshift__", ("n", None), formula
    )
    sink = Marking()
    pieces.start(sink, alone=alone)
    if recording:
        losses.start(sink, alone=alone)
    try:
        yield sink
    finally:
        losses.forget()
        pieces.forget()
        escapes.forget()
        CALLS_IN_USE.clear()


def tracked(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt.made(value, expression="n", sink=sink)


def downgrades(sink: list[SinkItem]) -> list[Downgrade]:
    return [item for item in sink if type(item) is Downgrade]


def drops(sink: list[SinkItem]) -> list[FormulaDrop]:
    return [item for item in sink if type(item) is FormulaDrop]


def forks(sink: list[SinkItem]) -> list[Branch]:
    return [item for item in sink if type(item) is Branch]


def test_a_match_hands_the_target_the_real_answer_tracked_with_the_formula_s_term() -> None:
    with using(by_four) as sink:
        k = quarter(tracked(13, sink))

    assert type(k) is ConcolicInt
    assert (int.__int__(k), k.expression, k.sink) == (3, ["//", "n", 4], sink)
    assert downgrades(sink) == []
    assert drops(sink) == []


def test_a_fork_the_formula_records_sits_at_the_site_and_is_marked() -> None:
    with using(capped) as sink:
        quarter(tracked(13, sink))

    [fork] = forks(sink)
    assert (fork.site, fork.expression, fork.taken, fork.summary) == (
        QUARTER,
        [">", ["//", "n", 4], 9],
        False,
        True,
    )


def test_a_later_fork_that_reads_the_formula_s_term_is_marked() -> None:
    with using(by_four) as sink:
        k = quarter(tracked(13, sink))
        _ = bool(k == 7)
        _ = bool(tracked(1, sink) == 2)

    assert [(fork.expression, fork.summary) for fork in forks(sink)] == [
        (["==", ["//", "n", 4], 7], True),
        (["==", "n", 2], False),
    ]


def raising(values: Mapping[str, object]) -> Mapping[str, object]:
    raise ValueError("no")


def test_a_mismatch_a_raise_and_a_missing_answer_each_drop_the_formula() -> None:
    cases: list[tuple[Formula, str, DropReason]] = [
        (squared, "169", DropReason.MISMATCH),
        (raising, "ValueError", DropReason.RAISED),
        (lambda values: {}, "", DropReason.MISSING),
        # an answer with no JSON text, written as Python writes it, cut short
        (lambda values: {"answer": (3, 1)}, "(3, 1)", DropReason.MISMATCH),
        (
            lambda values: {"answer": tuple(range(99))},
            "(0, 1, 2, 3, 4, 5, ...)",
            DropReason.MISMATCH,
        ),
    ]
    for formula, got, reason in cases:
        with using(formula) as sink:
            k = quarter(tracked(13, sink))

        assert (type(k), k) == (int, 3)
        assert [(each.name, each.site) for each in downgrades(sink)] == [("__rshift__", QUARTER)]
        assert drops(sink) == [FormulaDrop(QUARTER, "answer", "3", got, reason, run=0)]


def test_a_dropped_site_is_not_used_again_in_the_input() -> None:
    calls: list[object] = []

    def counted(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values["n"])
        return squared(values)

    with using(counted) as sink:
        first = quarter(tracked(13, sink))
        second = quarter(tracked(5, sink))

    assert (type(first), type(second)) == (int, int)
    assert calls == [13]
    assert len(downgrades(sink)) == 2
    assert len(drops(sink)) == 1


def test_the_run_a_formula_drops_on_past_the_cap_is_recorded_before_its_drop() -> None:
    def small(values: Mapping[str, object]) -> Mapping[str, object]:
        n = values["n"]
        assert isinstance(n, int)
        return {"answer": n // 4 if n < 20 else -1}

    with using(small) as sink:
        for each in range(MOST_RUNS):
            quarter(tracked(each, sink))
        quarter(tracked(21, sink))

    runs = [item for item in sink if type(item) is LossRun]
    assert len(runs) == MOST_RUNS + 1
    assert runs[-1].going_in[0].value == "21"
    [drop] = drops(sink)
    assert drop == FormulaDrop(QUARTER, "answer", "5", "-1", DropReason.MISMATCH, run=MOST_RUNS)
    assert sink.index(drop) > sink.index(runs[-1])


def test_a_formula_that_reaches_its_own_site_does_not_call_itself() -> None:
    calls: list[object] = []

    def again(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values["n"])
        n = values["n"]
        assert isinstance(n, int)
        return {"answer": quarter(n)}

    with using(again) as sink:
        k = quarter(tracked(13, sink))

    assert calls == [13]
    assert (type(k), k) == (int, 3)
    assert len([item for item in sink if type(item) is LossRun]) == 1
    assert drops(sink) == []


class Level(enum.IntEnum):
    LOW = 3


def test_only_a_real_answer_of_an_exact_int_float_str_or_bool_is_tracked() -> None:
    lost = Downgrade(name="__rshift__", site=QUARTER)
    with using(by_four) as sink:
        n = tracked(13, sink)
        member, member_drop = calls_in_use.answered(lost, (n, 2), Level.LOW)
        plain, plain_drop = calls_in_use.answered(lost, (n, 2), 3)

    assert (member, member_drop) == (Level.LOW, None)
    assert type(member) is Level
    assert (type(plain), plain_drop) == (ConcolicInt, None)


def test_values_whose_count_differs_from_the_formula_s_positions_get_the_real_answer() -> None:
    lost = Downgrade(name="__rshift__", site=QUARTER)
    with using(squared) as sink:
        got = calls_in_use.answered(lost, (tracked(13, sink),), 3)

    assert got == (3, None)
    assert drops(sink) == []


def test_a_call_that_does_not_run_alone_uses_no_site() -> None:
    with using(by_four, alone=False) as sink:
        k = quarter(tracked(13, sink))

    assert (type(k), k) == (int, 3)
    assert len(downgrades(sink)) == 1


def test_with_the_slot_empty_no_site_is_used() -> None:
    calls: list[object] = []

    def counted(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return by_four(values)

    with using(counted, recording=False) as sink:
        k = quarter(tracked(13, sink))

    assert (type(k), calls) == (int, [])
    assert len(downgrades(sink)) == 1


def test_a_match_still_escapes_the_walk_keys_handed_out() -> None:
    with using(by_four) as sink:
        key = ConcolicInt.made(13, expression=["key", "d", 0], sink=sink)
        escapes.handed_into(sink, key)
        k = quarter(key)
        escaped = escapes.has_escaped(key)

    assert type(k) is ConcolicInt
    assert escaped
    assert [item.expression for item in sink if type(item) is Fact] == [["==", ["key", "d", 0], 13]]
    assert downgrades(sink) == []
