"""Acceptance tests for the summarize-a-lost-call story through ``run()``: what an ask about a loss
site holds, the code with the site marked, its callee's source or name, its parameters and its
runs, and what stderr says of its try.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs and each input forked; no test calls a model.
"""

import inspect
import textwrap

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.llm.summaries import request_text
from pyct.run.code_context import marks
from pyct.run.summary_asks import SummaryRequest
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import (
    BINNED,
    DEDENTED,
    HALF,
    MOD,
    QUARTER,
    SHIFTED,
    SQUARED,
    at,
    place,
    places,
)

ABOVE, BELOW = marks("call")


def asked_at(provider: FakeSummaries, line: int, col: int) -> SummaryRequest:
    [request] = [each for each in provider.requests if each.place == place(line, col)]
    return request


# llm-summary-for-a-call-pyct-cannot-follow-asks-at-a-site-in-another-function
def test_the_ask_s_place_is_the_loss_s_in_the_function_that_holds_it() -> None:
    provider = FakeSummaries([QUARTER])

    run_summaries(SHIFTED, {"n": 3}, provider)

    request = asked_at(provider, 11, 11)
    assert request.code.startswith(
        "# targets.summaries.calls._quarter\n"
        "def _quarter(n: int) -> int:\n"
        f"    {ABOVE}\n"
        "    return n >> 2\n"
        f"    {BELOW}"
    )


# llm-summary-for-a-call-pyct-cannot-follow-asks-at-a-call-in-the-same-function, where the loss is
# `pow`'s own `__pow__` on the tracked int, recorded inside the call, so the call records none
def test_a_loss_at_a_call_in_the_same_function_is_asked_about_and_checked() -> None:
    provider = FakeSummaries([MOD])

    done = run_summaries(SQUARED, {"n": 2}, provider)

    site = at(29, 8)
    read = f"llm: summary for the call __pow__ at {site}: answer = n * n % 10"
    checked = f"llm: summary for the call __pow__ at {site}: checked on 1 past runs"
    said = done.llm_said()
    assert said.index(read) + 1 == said.index(checked)


# llm-summary-for-a-call-pyct-cannot-follow-request-names-a-c-callee
def test_the_ask_names_a_callee_written_in_c_with_no_source() -> None:
    provider = FakeSummaries([HALF])

    run_summaries(BINNED, {"n": 2}, provider)

    request = asked_at(provider, 22, 8)
    assert request.code.startswith(
        f"# targets.summaries.calls.binned\ndef binned(n: int) -> str:\n    {ABOVE}\n"
        f"    t = bin(n)\n    {BELOW}\n"
    )
    assert request.parameters == ("n",)
    text = request_text(request)
    assert "The call's callee is builtins.bin, whose source is not shown." in text
    assert '\nn = 2  ->  answer = "0b10"\n' in text
    assert "def bin(" not in text


# llm-summary-for-a-call-pyct-cannot-follow-request-names-a-c-callee, for the loss inside `pow`
def test_the_ask_about_a_loss_at_pow_names_its_one_parameter_and_its_run() -> None:
    provider = FakeSummaries([MOD])

    run_summaries(SQUARED, {"n": 2}, provider)

    request = asked_at(provider, 29, 8)
    assert f"    {ABOVE}\n    r = pow(n, 2, 10)\n    {BELOW}" in request.code
    assert request.parameters == ("n",)
    assert "\nn = 2  ->  answer = 4\n" in request_text(request)


# llm-summary-for-a-call-pyct-cannot-follow-request-holds-a-python-callee-s-source
def test_the_ask_holds_a_python_callee_s_source_after_the_function_s_code() -> None:
    provider = FakeSummaries([HALF])

    run_summaries(DEDENTED, {"s": "  ab"}, provider)

    request = asked_at(provider, 63, 8)
    source = textwrap.dedent(inspect.getsource(textwrap.dedent)).rstrip()
    assert request.code.index("def dedented(") < request.code.index(source)
    assert f"# textwrap.dedent\n{source}" in request.code
    assert "then the source of its callee, textwrap.dedent" in request_text(request)


# llm-summary-for-a-call-pyct-cannot-follow-failed-try-not-asked-again
def test_a_failed_try_ends_the_site_s_asks_for_the_run() -> None:
    provider = FakeSummaries([HALF])

    done = run_summaries(SHIFTED, [{"n": 3}, {"n": 9}], provider, Limits(budget=Budget(5)))

    failed = (
        f"llm: summary for the call __rshift__ at {at(11, 11)}, try 1:"
        " at input 1, answer was 0, the formula gave 1"
    )
    assert failed in done.llm_said()
    assert places(provider) == [place(11, 11)]
