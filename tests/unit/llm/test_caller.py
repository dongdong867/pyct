"""WorkerCaller asks through one worker process per ask, and each failure comes back a value."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.config.llm import Model
from pyct.llm.caller import WorkerCaller, _answer
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from tests.acceptance.llm_stub import DUMMY_KEY, Stub, closed_port, serving

TOOL = Tool("seeds", 4000)


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[Stub]:
    with serving(Stub(reply='[{"x": 1}]', tokens=(1200, 300))) as running:
        monkeypatch.setenv("OPENAI_BASE_URL", running.openai_url)
        monkeypatch.setenv("ANTHROPIC_BASE_URL", running.anthropic_url)
        monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)
        monkeypatch.setenv("ANTHROPIC_API_KEY", DUMMY_KEY)
        yield running


def test_an_openai_ask_sends_one_user_message_with_the_cap_and_nothing_stored(stub: Stub) -> None:
    answer = WorkerCaller(Model("openai", "gpt-6-luna")).call(TOOL, "m::f", 1, "the request")

    assert isinstance(answer, Reply)
    assert answer.text == '[{"x": 1}]'
    assert (answer.cost.attempt, answer.cost.tokens_in, answer.cost.tokens_out) == (1, 1200, 300)
    assert answer.cost.seconds > 0
    [received] = stub.received
    assert received.path == "/v1/responses"
    # no sampling setting, no system message, no tools
    assert received.body == {
        "model": "gpt-6-luna",
        "input": [{"role": "user", "content": "the request"}],
        "store": False,
        "max_output_tokens": 4000,
    }


def test_an_anthropic_ask_sends_one_user_message_with_the_cap(stub: Stub) -> None:
    answer = WorkerCaller(Model("anthropic", "claude-sonnet-5-5")).call(TOOL, "m::f", 2, "asked")

    assert isinstance(answer, Reply)
    assert answer.text == '[{"x": 1}]'
    assert (answer.cost.attempt, answer.cost.tokens_in, answer.cost.tokens_out) == (2, 1200, 300)
    [received] = stub.received
    assert received.path == "/v1/messages"
    assert received.body == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": "asked"}],
    }


def test_a_reply_with_no_usage_counts_no_tokens(stub: Stub) -> None:
    stub.tokens = None

    answer = WorkerCaller(Model("openai", "gpt-6-luna")).call(TOOL, "m::f", 1, "the request")

    assert isinstance(answer, Reply)
    assert (answer.cost.tokens_in, answer.cost.tokens_out) == (0, 0)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_a_refused_key_is_the_error_s_class_and_status(stub: Stub, provider: str) -> None:
    stub.status = 401

    answer = WorkerCaller(Model(provider, "m")).call(TOOL, "m::f", 1, "the request")

    assert answer == Unanswered(Why.PROVIDER, "AuthenticationError (401)", answer.cost)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_a_provider_that_cannot_be_reached_is_the_error_s_class(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    port = closed_port()
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", DUMMY_KEY)

    answer = WorkerCaller(Model(provider, "m")).call(TOOL, "m::f", 1, "the request")

    assert answer == Unanswered(Why.PROVIDER, "APIConnectionError", answer.cost)


def test_an_ask_with_no_reply_in_its_limit_ends_there(stub: Stub) -> None:
    stub.delay = 10

    answer = WorkerCaller(Model("openai", "m"), seconds=2).call(TOOL, "m::f", 3, "the request")

    assert answer == Unanswered(Why.TIMED_OUT, "no reply in 2 s", answer.cost)
    assert answer.cost.attempt == 3
    assert 2 <= answer.cost.seconds < 4


@pytest.mark.parametrize("stdout", ["", "not json", "[1]", '{"other": 1}'])
def test_a_worker_that_prints_no_reply_is_said_with_its_exit(stdout: str) -> None:
    done = subprocess.CompletedProcess(["python"], 1, stdout=stdout, stderr="")

    answer = _answer(done, 1, 0.5)

    assert answer == Unanswered(
        Why.PROVIDER, "the worker gave no reply (exit 1)", AskCost(1, seconds=0.5)
    )


def test_a_provider_error_with_no_status_is_its_class_alone() -> None:
    done = subprocess.CompletedProcess(["python"], 0, stdout='{"error": "APIConnectionError"}')

    answer = _answer(done, 1, 0.5)

    assert answer == Unanswered(Why.PROVIDER, "APIConnectionError", AskCost(1, seconds=0.5))


def test_a_worker_that_cannot_start_is_the_error_s_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-python"))

    answer = WorkerCaller(Model("openai", "m")).call(TOOL, "m::f", 1, "the request")

    assert answer == Unanswered(
        Why.PROVIDER, "the worker could not start (FileNotFoundError)", answer.cost
    )
