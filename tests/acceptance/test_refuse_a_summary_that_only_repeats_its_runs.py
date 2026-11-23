"""Acceptance tests for the refuse-a-summary-that-only-repeats-its-runs story through ``run()``:
a summaries request holds back the runs whose values going in are the latest complete run's, the
check still runs the formula on them, and stderr counts the runs the request did not show.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs; no test calls a model.
"""

import json
from dataclasses import dataclass

from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse, Unanswered
from pyct.results.record import InputRecord
from pyct.run.summaries import ShownRun, SummaryReply, SummaryRequest
from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
    F,
    FakeSummaries,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)

# `H` of the criteria, and its loop's line
H = str(REPO_ROOT / "targets" / "summaries" / "one_run.py")
Z_BYTES = "targets.summaries.one_run::z_bytes"
H_LOOP = 7


@dataclass
class Lookup(FakeSummaries):
    """Answers each ask with the lookup reply: the runs its request shows written down, each
    shown run's ``t`` for its ``s``, and -1 for any other ``s``."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        self.replies = [code_reply(lookup(request.runs))]
        return super().summarize(request)


def lookup(runs: tuple[ShownRun, ...]) -> str:
    table = {dict(run.going_in)["s"]: int(dict(run.changed)["t"]) for run in runs}
    terms = "".join(f" + (s == {s}) * {t + 1}" for s, t in table.items())
    return f'def summary(s, t):\n    t = -1{terms}\n    return {{"t": t}}'


def s_of(record: InputRecord) -> str:
    s = record.args["s"]
    assert isinstance(s, str)
    return s


def shown(record: InputRecord) -> ShownRun:
    """An input of ``counts`` as its loop's run, shown in a request."""
    s = s_of(record)
    return ShownRun((("s", json.dumps(s)), ("t", "0")), (("t", str(s.count("z"))),))


def before_the_ask(done: Summarized, provider: FakeSummaries) -> list[InputRecord]:
    """The inputs the run had when the first ask came, each with one complete run of the loop;
    the latest's ``s`` is held back."""
    before = done.records[: provider.inputs_then[0]]
    assert len({s_of(record) for record in before}) > 1
    return before


# llm-summary-held-out-run-not-shown
def test_the_request_holds_back_the_runs_with_the_latest_run_s_values_going_in() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider)

    before = before_the_ask(done, provider)
    latest = s_of(before[-1])
    others = {shown(record) for record in before if s_of(record) != latest}
    assert len(others) <= 10
    [request] = provider.requests
    assert set(request.runs) == others
    assert all(dict(run.going_in)["s"] != json.dumps(latest) for run in request.runs)


# llm-summary-held-out-lookup-table-fails
def test_a_formula_that_writes_down_the_runs_shown_fails_on_a_run_held_back() -> None:
    provider = Lookup([])

    done = run_summaries(COUNTS, SEED, provider)

    before = before_the_ask(done, provider)
    latest = s_of(before[-1])
    at = next(number for number, each in enumerate(before, 1) if s_of(each) == latest)
    failed = f"at input {at}, t was {latest.count('z')}, the formula gave -1"
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

    done = run_summaries(Z_BYTES, SEED, provider)

    [request] = provider.requests
    assert provider.inputs_then == [1]
    assert request.runs == (ShownRun((("s", '"ab"'), ("t", "0")), (("t", "0"),)),)
    checked = f"llm: summary for the loop at {H}:{H_LOOP}: checked on 1 past runs"
    assert checked in done.said
    assert not any(line.startswith(f"{checked},") for line in done.said)
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    [item] = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    assert item["state"] == "in use"
