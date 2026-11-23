"""Acceptance tests for the refuse-a-summary-that-only-repeats-its-runs story through ``run()``:
a summaries request holds back the runs whose values going in are the latest complete run's, the
check still runs the formula on them, and stderr counts the runs the request did not show.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs; no test calls a model.
"""

import json
from dataclasses import dataclass

from pyct.llm.summaries import request_text
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse, Unanswered
from pyct.results.record import InputRecord
from pyct.run.isolation import Isolation
from pyct.run.summaries import ShownRun, SummaryReply, SummaryRequest
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
    F,
    FakeSummaries,
    G,
    Summarized,
    code_reply,
    held_back,
    one_thread,  # noqa: F401
    run_summaries,
)

# `encoded_z` of the criteria, whose loop records no fork, and its loop's line
ENCODED_Z = "targets.summaries.loops::encoded_z"
STOPS = "targets.summaries.loops::stops"
ENCODED_Z_LOOP = 132


@dataclass
class Lookup(FakeSummaries):
    """Answers each ask with the lookup reply: the runs its request shows written down, each
    shown run's ``t`` for its ``s``, and ``t`` as it came in for any other ``s``."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        self.replies = [code_reply(lookup(request.runs))]
        return super().summarize(request)


def lookup(runs: tuple[ShownRun, ...]) -> str:
    table = {dict(run.going_in)["s"]: int(dict(run.changed)["t"]) for run in runs}
    terms = "".join(f" + (s == {s}) * {t}" for s, t in table.items())
    return f'def summary(s, t):\n    t = t{terms}\n    return {{"t": t}}'


def s_of(record: InputRecord) -> str:
    s = record.args["s"]
    assert isinstance(s, str)
    return s


def shown(record: InputRecord) -> ShownRun:
    """An input of ``counts`` as its loop's run, shown in a request."""
    s = s_of(record)
    return ShownRun((("s", json.dumps(s)), ("t", "0")), (("t", str(s.count("z"))),))


def before_the_ask(done: Summarized, provider: FakeSummaries) -> list[InputRecord]:
    """The inputs the run had when the first ask came, each with one complete run of the loop."""
    before = done.records[: provider.inputs_then[0]]
    assert len({s_of(record) for record in before}) > 1
    return before


def held_s(before: list[InputRecord]) -> str:
    """The ``s`` the request held back from these inputs' runs."""
    return json.loads(dict(held_back([shown(record) for record in before]))["s"])


# llm-summary-held-out-run-not-shown
def test_the_request_holds_back_the_latest_run_whose_changed_values_no_other_run_has() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider)

    before = before_the_ask(done, provider)
    held = held_s(before)
    others = {shown(record) for record in before if s_of(record) != held}
    assert len(others) <= 10
    [request] = provider.requests
    assert set(request.runs) == others


# llm-summary-held-out-lookup-table-fails
def test_a_formula_that_writes_down_the_runs_shown_fails_on_a_run_held_back() -> None:
    provider = Lookup([])

    done = run_summaries(COUNTS, SEED, provider)

    before = before_the_ask(done, provider)
    held = held_s(before)
    assert held.count("z") != 0
    at = next(number for number, each in enumerate(before, 1) if s_of(each) == held)
    failed = f"at input {at}, t was {held.count('z')}, the formula gave 0"
    assert f"llm: summary for the loop at {F}:10, try 1: {failed}" in done.said
    assert not any("checked on" in line for line in done.said)


# llm-summary-held-out-count-said
def test_the_checked_line_counts_the_runs_the_request_did_not_show() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider)

    before = before_the_ask(done, provider)
    [request] = provider.requests
    seen = {run.going_in for run in request.runs}
    hidden = sum(shown(record).going_in not in seen for record in before)
    assert hidden >= 1
    checked = f"checked on {len(before)} past runs, {hidden} of them not shown"
    assert f"llm: summary for the loop at {F}:10: {checked}" in done.said


# llm-summary-held-out-one-run
def test_a_loop_with_one_complete_run_is_asked_about_with_it_and_its_formula_comes_into_use() -> (
    None
):
    provider = FakeSummaries([COUNT])

    done = run_summaries(ENCODED_Z, SEED, provider)

    [request] = provider.requests
    assert provider.inputs_then == [1]
    assert request.runs == (ShownRun((("s", '"ab"'), ("t", "0")), (("t", "0"),)),)
    # nothing is held back, so the request makes no claim about runs it does not show
    assert "does not show" not in request_text(request)
    checked = f"llm: summary for the loop at {G}:{ENCODED_Z_LOOP}: checked on 1 past runs"
    assert checked in done.said
    assert not any(line.startswith(f"{checked},") for line in done.said)
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    [item] = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    assert item["state"] == "in use"


# llm-summary-held-out-request-says-so
def test_the_request_says_runs_it_does_not_show_are_checked() -> None:
    provider = FakeSummaries([COUNT])

    run_summaries(COUNTS, SEED, provider)

    [request] = provider.requests
    assert request.not_shown >= 1
    text = request_text(request)
    assert "and ones this request does not show" in text
    assert "a formula that only writes down the runs shown can fail" in text


# llm-summary-never-used-loop-that-returns
def test_a_loop_whose_own_code_returns_is_not_asked_about() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(STOPS, SEED, provider)

    assert provider.requests == []
    skipped = f"llm: summary for the loop at {G}:22 skipped: the loop holds a return"
    assert done.said.count(skipped) == 1


# llm-summary-never-used-in-pyct-s-process
def test_no_loop_is_asked_about_while_inputs_run_in_pyct_s_process() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider, isolation=Isolation.IN_PROCESS)

    assert provider.requests == []
    skipped = f"llm: summary for the loop at {F}:10 skipped: inputs run in pyct's own process"
    assert done.said.count(skipped) == 1
