"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``run()``: at a stuck
moment pyct asks about each loop a ``no fork`` cause names, with the loop's code and its
recorded runs, and says what it skipped or ignored.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs; no test calls a model.
"""

import json
import threading
from collections.abc import Iterator

import pytest

from pyct.llm.summaries import FOLLOWS, request_text
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import InputRecord, StopKind
from pyct.run import model_runs, threads
from pyct.run.code_context import MARK_END, MARK_START
from pyct.run.summaries import ShownRun
from pyct.run.summary_checks import answer_form
from tests.acceptance.llm_summaries import (
    COUNTS,
    SEED,
    F,
    FakeSummaries,
    G,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)

TALLIES = "targets.summaries.loops::tallies"
STOPS = "targets.summaries.loops::stops"
VOWELS = "targets.summaries.loops::vowels"
# a formula the checks would refuse, for a test about the ask alone
ANY = code_reply('def summary(s, t):\n    return {"t": t}')


def shown(record: InputRecord) -> ShownRun:
    """An input of ``counts`` as its loop's run, shown in a request."""
    s = record.args["s"]
    assert isinstance(s, str)
    return ShownRun((("s", json.dumps(s)), ("t", "0")), (("t", str(s.count("z"))),))


# llm-summary-for-a-stuck-loop-sends-the-loop-and-its-runs
def test_the_request_holds_the_loop_its_names_its_runs_the_form_and_what_pyct_follows() -> None:
    provider = FakeSummaries([ANY])

    done = run_summaries(COUNTS, SEED, provider)

    [request] = provider.requests
    assert request.place == "targets.why.stuck:10:4"
    assert request.code == (
        "# targets.why.stuck.counts\n"
        "def counts(s: str) -> str:\n"
        "    t = 0\n"
        f"    {MARK_START}\n"
        "    for c in s:\n"
        '        if c == "z":\n'
        "            t += 1\n"
        f"    {MARK_END}\n"
        "    if t > 25:\n"
        '        return "many"\n'
        '    return "few"'
    )
    assert (request.parameters, request.changed) == (("s", "t"), ("t",))
    before = done.records[: provider.inputs_then[0]]
    assert 1 < len(before) <= 10
    assert request.runs == tuple(shown(record) for record in before)
    text = request_text(request)
    assert FOLLOWS in text
    assert answer_form(("s", "t"), ("t",)) in text


# llm-summary-for-a-stuck-loop-sends-ten-runs-at-most
def test_the_request_holds_ten_runs_those_whose_values_going_in_differ_first() -> None:
    seeds = [{"s": "zz"}] * 3 + [{"s": letter} for letter in "abcdefghi"]
    provider = FakeSummaries([ANY])

    done = run_summaries(COUNTS, seeds, provider)

    [request] = provider.requests
    assert provider.inputs_then[0] > 12
    assert request.runs == tuple(shown(record) for record in done.records[2:12])


# llm-summary-for-a-stuck-loop-one-ask-per-loop
def test_a_loop_two_missed_lines_name_is_asked_about_once_for_both_its_values() -> None:
    provider = FakeSummaries([code_reply('def summary(s, ups, downs):\n    return {"ups": 0}')])

    run_summaries(TALLIES, SEED, provider)

    [request] = provider.requests
    assert request.place == "targets.summaries.loops:8:4"
    assert (request.parameters, request.changed) == (("downs", "s", "ups"), ("downs", "ups"))


# llm-summary-for-a-stuck-loop-loop-that-returns
def test_the_request_holds_only_the_runs_in_which_the_loop_ended() -> None:
    provider = FakeSummaries([ANY])

    done = run_summaries(STOPS, SEED, provider)

    [request] = provider.requests
    before = done.records[: provider.inputs_then[0]]
    ended = [record for record in before if "!" not in str(record.args["s"])]
    assert len(ended) < len(before)
    assert request.runs == tuple(shown(record) for record in ended)[:10]


# llm-summary-for-a-stuck-loop-no-recorded-run
def test_a_loop_no_run_of_which_was_recorded_is_not_asked_about() -> None:
    provider = FakeSummaries([ANY])

    done = run_summaries(VOWELS, SEED, provider)

    assert provider.requests == []
    assert f"llm: summary for the loop at {G}:35 skipped: no recorded run" in done.said


@pytest.fixture
def second_thread(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A second thread in pyct's process for the test's length, counted as a run counts it."""
    monkeypatch.setattr(model_runs, "running", threads.running)
    done = threading.Event()
    waiting = threading.Thread(target=done.wait, daemon=True)
    waiting.start()
    yield
    done.set()
    waiting.join()


# llm-summary-for-a-stuck-loop-cannot-fork
@pytest.mark.usefixtures("second_thread")
def test_no_ask_is_made_while_pyct_s_process_runs_a_second_thread() -> None:
    provider = FakeSummaries([ANY])

    done = run_summaries(COUNTS, SEED, provider)

    assert provider.requests == []
    assert f"llm: summary for the loop at {F}:10 skipped: cannot fork" in done.said


# llm-summary-for-a-stuck-loop-reply-without-code
def test_a_reply_with_no_code_block_is_ignored_and_the_run_goes_on() -> None:
    provider = FakeSummaries(["t is the number of z in s"])

    done = run_summaries(COUNTS, SEED, provider)

    said = done.llm_said()
    assert "llm: summaries reply ignored: no code block" in said
    assert not any(line.startswith("llm: summary for") for line in said)
    assert done.result.stopped.kind is StopKind.NO_GAIN
    assert len(done.records) > provider.inputs_then[0]


# llm-summary-for-a-stuck-loop-goes-on-after-a-failed-ask
def test_a_failed_ask_is_said_and_the_run_goes_on() -> None:
    failed = Unanswered(Why.PROVIDER, "provider error 500", AskCost(1))
    provider = FakeSummaries([failed])

    done = run_summaries(COUNTS, SEED, provider)

    said = done.llm_said()
    assert "llm: summaries ask skipped: provider error 500" in said
    assert not any(line.startswith("llm: summary for") for line in said)
    assert done.result.stopped.kind is StopKind.NO_GAIN
    assert len(done.records) > provider.inputs_then[0]
