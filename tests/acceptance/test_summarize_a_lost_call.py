"""Acceptance tests for the summarize-a-lost-call story through ``run()``: as soon as an input
records a run of a loss site, pyct asks about it, before the next pick and with no stuck moment,
once per run, in the order recorded, whether or not a line needs it, and skips the sites a
formula cannot stand for.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs and each input forked; no test calls a model.
"""

import json
import textwrap
import time
from pathlib import Path

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.run.summary_asks import SummaryReply, SummaryRequest
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    Summarized,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import (
    DEEP,
    HALF,
    LATE,
    MATCHED,
    MEASURED,
    QUARTER,
    SHIFTED,
    WRAPPED,
    at,
    place,
    places,
)


def said_about(done: Summarized, site: str) -> list[str]:
    """The ``llm: summary for the call`` lines about the site written ``file:line:col``."""
    return [line for line in done.llm_said() if f" at {site}" in line and "the call" in line]


# llm-summary-for-a-call-pyct-cannot-follow-asks-without-a-stuck-moment
def test_pyct_asks_about_a_loss_after_the_seed_and_before_any_other_input() -> None:
    provider = FakeSummaries([QUARTER])

    done = run_summaries(SHIFTED, {"n": 3}, provider)

    site = at(11, 11)
    read = f"llm: summary for the call __rshift__ at {site}: answer = n // 4"
    checked = f"llm: summary for the call __rshift__ at {site}: checked on 1 past runs"
    assert done.said.index("input 1") < done.said.index(read) < done.said.index(checked)
    assert "input 2" not in done.said[: done.said.index(checked)]
    assert provider.inputs_then == [1]


# llm-summary-for-a-call-pyct-cannot-follow-asks-whether-or-not-a-line-needs-it
def test_pyct_asks_about_a_loss_no_missed_line_reads() -> None:
    provider = FakeSummaries([HALF])

    run_summaries(LATE, {"s": "a", "n": 3}, provider)

    assert place(53, 11) in places(provider)


# llm-summary-for-a-call-pyct-cannot-follow-asks-in-the-order-recorded
def test_pyct_asks_about_each_loss_in_the_order_the_input_recorded_them() -> None:
    provider = FakeSummaries([HALF])

    run_summaries(DEEP, {"n": 3}, provider)

    assert places(provider) == [place(36, 8), place(37, 8), place(38, 8), place(40, 11)]
    assert provider.inputs_then == [1, 1, 1, 1]


# llm-summary-for-a-call-pyct-cannot-follow-asks-once-per-run
def test_pyct_asks_about_a_loss_once_in_a_run_whose_every_input_records_it() -> None:
    provider = FakeSummaries([HALF])

    done = run_summaries(
        SHIFTED, [{"n": 3}, {"n": 9}, {"n": 30}], provider, Limits(budget=Budget(5))
    )

    assert len(done.records) == 3
    assert all(record.losses for record in done.records)
    assert places(provider) == [place(11, 11)]


# llm-summary-for-a-call-pyct-cannot-follow-asks-at-a-library-site
def test_pyct_asks_about_a_loss_inside_the_standard_library() -> None:
    provider = FakeSummaries([HALF])
    lines = Path(textwrap.__file__).read_text(encoding="utf-8").splitlines()
    line = next(at for at, text in enumerate(lines, start=1) if "text.expandtabs(" in text)
    col = lines[line - 1].index("text.expandtabs(")

    run_summaries(WRAPPED, {"s": "a\tb"}, provider)

    [request] = [each for each in provider.requests if each.place == f"textwrap:{line}:{col}"]
    assert request.code.startswith("# textwrap.TextWrapper._munge_whitespace\n")
    assert "text = text.expandtabs(" in request.code
    assert request.parameters == ("text", "arg2")


# llm-summary-for-a-call-pyct-cannot-follow-skipped-answer-python-converts
def test_a_site_whose_answer_python_converts_gets_no_ask_and_is_said_once() -> None:
    provider = FakeSummaries([HALF])

    done = run_summaries(MEASURED, [{"s": '{"k": 1}'}, {"s": '{"k": 2}'}], provider)

    skipped = [line for line in done.llm_said() if "skipped: Python converts its answer" in line]
    assert len(skipped) == 1
    assert skipped[0].startswith(f"llm: summary for the call __len__ at {json.decoder.__file__}:")
    assert not [each for each in provider.requests if each.place.startswith("json.")]


# llm-summary-for-a-call-pyct-cannot-follow-skipped-answer-not-a-scalar
def test_a_site_whose_answer_is_a_list_gets_no_ask_and_is_said_once() -> None:
    provider = FakeSummaries([HALF])

    done = run_summaries(MATCHED, [{"s": "ab"}, {"s": "ba"}], provider)

    site = at(77, 8)
    assert said_about(done, site) == [
        f"llm: summary for the call re.findall at {site} skipped: the answer is a list"
    ]
    assert place(77, 8) not in places(provider)


class Waiting(FakeSummaries):
    """A fake whose every ask waits ``seconds`` for its reply."""

    seconds = 8.0

    def summarize(self, request: SummaryRequest) -> SummaryReply:
        time.sleep(self.seconds)
        reply = super().summarize(request)
        assert isinstance(reply, SummaryReply)
        return reply


# llm-summary-for-a-call-pyct-cannot-follow-wait-not-counted
def test_the_wait_for_a_loss_site_s_reply_is_added_back_to_the_budget() -> None:
    provider = Waiting([QUARTER])
    started = time.monotonic()

    done = run_summaries(SHIFTED, {"n": 3}, provider, Limits(budget=Budget(10)))

    assert provider.requests
    deadline = done.result.deadline
    assert deadline is not None
    assert deadline - started >= 10 + Waiting.seconds
