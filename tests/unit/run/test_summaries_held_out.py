"""The runs a summaries request holds back: those whose values going in are the latest complete
run's, so that a formula that writes down the runs shown fails on them, and the count of runs
the request did not show."""

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun
from pyct.results.llm_asks import AskCost
from pyct.run.notes import SummaryChecked, SummaryFailed
from pyct.run.summaries import SummaryReply
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_runs import AskedLoop, ShownRun, not_shown, piece_at, shown_runs
from tests.unit.run.test_summaries import (
    LOOP,
    LOOPED,
    Fake,
    counted,
    entry,
    one_thread,  # noqa: F401
    record,
    taken,
)

FORMULA = 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'
# `counts`'s loop on "ab" written down, and 9 for any other `s`
# a lookup of the runs "ab" and "a" show that leaves `t` as it came in for any other `s`
FALLS_THROUGH = 'def summary(s, t):\n    if s == "a":\n        t = 0\n    return {"t": t}\n'
LOOKUP = 'def summary(s, t):\n    t = 9 - (s == "ab") * 9\n    return {"t": t}\n'


def loop_of(*values: str) -> AskedLoop:
    """``counts``'s loop with one complete run on each of the values, from input 1 on."""
    piece = piece_at(LOOP)
    assert piece is not None
    runs = tuple(CompleteRun(at, counted(s)) for at, s in enumerate(values, start=1))
    return AskedLoop(LOOP, piece, runs, ("s", "t"))


def on(s: str) -> ShownRun:
    return ShownRun((("s", f'"{s}"'), ("t", "0")), (("t", str(s.count("z"))),))


def test_the_runs_with_the_latest_run_s_values_going_in_are_held_back() -> None:
    loop = loop_of("zz", "a", "zz", "b", "zz")

    assert shown_runs(loop) == (on("a"), on("b"))
    assert not_shown(loop, shown_runs(loop)) == 3


def test_runs_whose_values_going_in_are_all_the_same_are_all_shown() -> None:
    loop = loop_of("zz", "zz")

    assert shown_runs(loop) == (on("zz"), on("zz"))
    assert not_shown(loop, shown_runs(loop)) == 0


def test_one_complete_run_is_shown() -> None:
    loop = loop_of("ab")

    assert shown_runs(loop) == (on("ab"),)
    assert not_shown(loop, shown_runs(loop)) == 0


def test_a_run_with_the_same_values_going_in_but_other_changed_values_is_held_back() -> None:
    piece = piece_at(LOOP)
    assert piece is not None
    other = PieceRun(
        LOOP, (GoingIn("s", '"b"', True), GoingIn("t", "0", False)), (Changed("t", "7"),)
    )
    runs = (CompleteRun(1, counted("a")), CompleteRun(2, other), CompleteRun(3, counted("b")))

    shown = shown_runs(AskedLoop(LOOP, piece, runs, ("s", "t")))

    assert shown == (on("a"),)


def test_the_run_a_formula_failed_on_stays_first_with_the_latest_values_going_in() -> None:
    loop = loop_of("a", "b", "zz")

    shown = shown_runs(loop, loop.runs[2])

    assert shown == (on("zz"), on("a"))
    assert not_shown(loop, shown) == 1


def test_nothing_is_held_back_when_only_the_failed_run_s_values_going_in_are_left() -> None:
    loop = loop_of("zz", "zz")

    assert shown_runs(loop, loop.runs[1]) == (on("zz"), on("zz"))


def test_past_ten_runs_the_count_holds_each_run_no_shown_run_has_the_values_of() -> None:
    loop = loop_of(*(str(at) for at in range(1, 14)))

    shown = shown_runs(loop)

    assert shown == tuple(on(str(at)) for at in range(1, 11))
    assert not_shown(loop, shown) == 3


def test_a_formula_that_writes_down_the_runs_shown_fails_on_a_run_held_back() -> None:
    fake = Fake(SummaryReply(LOOKUP, AskCost(1)))

    _, notes, _ = taken(fake, [entry(LOOPED)], [record(counted("ab")), record(counted("zz"))])

    [request] = fake.requests
    assert request.runs == (on("ab"),)
    assert SummaryFailed(LOOP, 1, "at input 2, t was 2, the formula gave 9") in notes


def test_the_checked_note_counts_the_runs_the_request_did_not_show() -> None:
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))

    _, notes, _ = taken(fake, [entry(LOOPED)], [record(counted("ab")), record(counted("zz"))])

    assert SummaryChecked(LOOP, 2, 1) in notes


def test_the_latest_run_whose_changed_values_no_other_run_has_is_held_back() -> None:
    loop = loop_of("ab", "z", "a")

    assert shown_runs(loop) == (on("ab"), on("a"))


def test_the_latest_run_is_held_back_when_each_run_s_changed_values_are_another_s_too() -> None:
    loop = loop_of("ab", "a")

    assert shown_runs(loop) == (on("ab"),)


def test_a_lookup_that_falls_through_fails_on_the_run_held_back() -> None:
    fake = Fake(SummaryReply(FALLS_THROUGH, AskCost(1)))
    runs = [record(counted("ab")), record(counted("z")), record(counted("a"))]

    _, notes, _ = taken(fake, [entry(LOOPED)], runs)

    [request] = fake.requests
    assert request.runs == (on("ab"), on("a"))
    assert SummaryFailed(LOOP, 1, "at input 2, t was 1, the formula gave 0") in notes
