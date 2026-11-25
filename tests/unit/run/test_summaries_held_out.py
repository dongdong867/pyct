"""The runs a summaries request holds back: those whose values going in are the latest complete
run's, so that a formula that writes down the runs shown fails on them, and the count of runs
the request did not show. Each run is of a call ``g(s, answer)``, whose ``answer`` goes in 0 and
comes out the count of z in ``s``."""

from pathlib import Path

import pytest

from pyct.core.foundation.branch import Changed, GoingIn, LossKind, LossRun, Site
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.call_summaries import AskedCall
from pyct.run.notes import Note, SummaryChecked, SummaryFailed
from pyct.run.summaries import SummaryReply, SummaryRequest
from pyct.run.summary_checks import AskedRun, CompleteRun
from pyct.run.summary_runs import ShownRun, not_shown, shown_runs
from tests.unit.run.test_summaries import (
    Fake,
    Run,
    no_site_in_use,  # noqa: F401
    one_thread,  # noqa: F401
    record,
    turned,
)

FORMULA = 'def summary(s, answer):\n    return {"answer": answer + s.count("z")}\n'
# a lookup of the runs "ab" and "a" show that leaves `answer` as it came in for any other `s`
FALLS_THROUGH = (
    'def summary(s, answer):\n    if s == "a":\n        answer = 0\n    return {"answer": answer}\n'
)
# the call on "ab" written down, and 9 for any other `s`
LOOKUP = (
    'def summary(s, answer):\n    answer = 9 - (s == "ab") * 9\n    return {"answer": answer}\n'
)


def counted(s: str) -> AskedRun:
    going_in = (GoingIn("s", f'"{s}"', True), GoingIn("answer", "0", False))
    return AskedRun(going_in, (Changed("answer", str(s.count("z"))),))


def call_of(*values: str) -> AskedCall:
    """The call with one complete run on each of the values, from input 1 on."""
    runs = tuple(CompleteRun(at, counted(s)) for at, s in enumerate(values, start=1))
    return call_with(runs)


def call_with(runs: tuple[CompleteRun, ...]) -> AskedCall:
    names = ("s", "answer")
    site = Site("m.py", 2, 11)
    return AskedCall(site, runs, names, (2, 2), "g", LossKind.CALL, "g(s, answer)", None, 0, names)


@pytest.fixture
def site(tmp_path: Path) -> Site:
    """The site of ``g(s, answer)`` in a module of its own."""
    module = tmp_path / "m.py"
    module.write_text("def f(s, answer):\n    return g(s, answer)\n")
    return Site(str(module), 2, 11)


def asked(fake: Fake, site: Site, *values: str) -> list[Note]:
    """The notes of the call's one ask, with one input that ran it on each of the values."""
    runs = [
        LossRun(
            site,
            "g",
            LossKind.CALL,
            (GoingIn("arg1", f'"{s}"', True), GoingIn("arg2", "0", False)),
            (Changed("answer", str(s.count("z"))),),
        )
        for s in values
    ]
    _, notes = turned(fake, Run([record(each) for each in runs]))
    return notes


def on(s: str) -> ShownRun:
    return ShownRun((("s", f'"{s}"'), ("answer", "0")), (("answer", str(s.count("z"))),))


def test_the_runs_with_the_latest_run_s_values_going_in_are_held_back() -> None:
    call = call_of("zz", "a", "zz", "b", "zz")

    assert shown_runs(call) == (on("a"), on("b"))
    assert not_shown(call, shown_runs(call)) == 3


def test_runs_whose_values_going_in_are_all_the_same_are_all_shown() -> None:
    call = call_of("zz", "zz")

    assert shown_runs(call) == (on("zz"), on("zz"))
    assert not_shown(call, shown_runs(call)) == 0


def test_one_complete_run_is_shown() -> None:
    call = call_of("ab")

    assert shown_runs(call) == (on("ab"),)
    assert not_shown(call, shown_runs(call)) == 0


def test_a_run_with_the_same_values_going_in_but_other_changed_values_is_held_back() -> None:
    other = AskedRun(
        (GoingIn("s", '"b"', True), GoingIn("answer", "0", False)), (Changed("answer", "7"),)
    )
    runs = (CompleteRun(1, counted("a")), CompleteRun(2, other), CompleteRun(3, counted("b")))

    shown = shown_runs(call_with(runs))

    assert shown == (on("a"),)


def test_the_run_a_formula_failed_on_stays_first_with_the_latest_values_going_in() -> None:
    call = call_of("a", "b", "zz")

    shown = shown_runs(call, call.runs[2])

    assert shown == (on("zz"), on("a"))
    assert not_shown(call, shown) == 1


def test_nothing_is_held_back_when_only_the_failed_run_s_values_going_in_are_left() -> None:
    call = call_of("zz", "zz")

    assert shown_runs(call, call.runs[1]) == (on("zz"), on("zz"))


def test_past_ten_runs_the_count_holds_each_run_no_shown_run_has_the_values_of() -> None:
    call = call_of(*(str(at) for at in range(1, 14)))

    shown = shown_runs(call)

    assert shown == tuple(on(str(at)) for at in range(1, 11))
    assert not_shown(call, shown) == 3


def test_a_formula_that_writes_down_the_runs_shown_fails_on_a_run_held_back(site: Site) -> None:
    fake = Fake(SummaryReply(LOOKUP, AskCost(1)))

    notes = asked(fake, site, "ab", "zz")

    [request] = fake.requests
    assert request.runs == (on("ab"),)
    reason = "at input 2, answer was 2, the formula gave 9"
    assert SummaryFailed(site, 1, reason, call="g") in notes


def test_the_checked_note_counts_the_runs_the_request_did_not_show(site: Site) -> None:
    fake = Fake(SummaryReply(FORMULA, AskCost(1)))

    notes = asked(fake, site, "ab", "zz")

    assert SummaryChecked(site, 2, 1, call="g") in notes


def test_the_latest_run_whose_changed_values_no_other_run_has_is_held_back() -> None:
    call = call_of("ab", "z", "a")

    assert shown_runs(call) == (on("ab"), on("a"))


def test_the_latest_run_is_held_back_when_each_run_s_changed_values_are_another_s_too() -> None:
    call = call_of("ab", "a")

    assert shown_runs(call) == (on("ab"),)


def test_a_lookup_that_falls_through_fails_on_the_run_held_back(site: Site) -> None:
    fake = Fake(SummaryReply(FALLS_THROUGH, AskCost(1)))

    notes = asked(fake, site, "ab", "z", "a")

    [request] = fake.requests
    assert request.runs == (on("ab"), on("a"))
    reason = "at input 2, answer was 1, the formula gave 0"
    assert SummaryFailed(site, 1, reason, call="g") in notes


class Lookup(Fake):
    """Answers with a lookup of the runs its request shows: each shown run's ``answer`` for its
    ``s``, and ``answer`` as it came in for any other ``s``."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        terms = "".join(
            f" + (s == {dict(run.going_in)['s']}) * {dict(run.changed)['answer']}"
            for run in request.runs
        )
        body = f"    answer = answer{terms}\n"
        code = f'def summary(s, answer):\n{body}    return {{"answer": answer}}\n'
        self.answer = SummaryReply(code, AskCost(1))
        return super().summarize(request)


def test_a_run_whose_answer_the_call_changed_is_held_back_before_one_it_left() -> None:
    # "ab" alone gives answer 0, but the call left answer as it came in, so a lookup that falls
    # through would pass on it; "az" changed answer
    call = call_of("ab", "zb", "az")

    assert shown_runs(call) == (on("ab"), on("zb"))


def test_a_lookup_of_the_runs_shown_fails_on_a_run_the_call_changed(site: Site) -> None:
    notes = asked(Lookup(), site, "ab", "zb", "az")

    reason = "at input 3, answer was 1, the formula gave 0"
    assert SummaryFailed(site, 1, reason, call="g") in notes
