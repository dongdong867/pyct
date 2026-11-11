"""How one ask reaches a model: a ``Caller``, and ``WorkerCaller``, which runs the worker."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Protocol

from pyct.config.llm import Model
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why

# the seconds one ask may wait for its reply, the worker's start included
WAIT_SECONDS = 30.0
# the worker's command after the interpreter: isolated, so no file in the target's folder,
# such as one named openai.py, is imported in its place
WORKER = ("-I", "-m", "pyct.llm.worker")


class Caller(Protocol):
    """Answers one ask: a reply, or why there is none. It never raises for an LLM problem."""

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered: ...


@dataclass(frozen=True)
class WorkerCaller:
    """Asks ``model`` through one worker process per ask, killed after ``seconds``.

    The worker inherits pyct's environment, so the key reaches the SDK only through the
    variable the SDK reads; pyct never reads it.
    """

    model: Model
    seconds: float = WAIT_SECONDS

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        request = {
            "provider": self.model.provider,
            "model": self.model.name,
            "text": text,
            "out_tokens": tool.out_tokens,
        }
        started = time.monotonic()
        try:
            done = subprocess.run(
                [sys.executable, *WORKER],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=self.seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            cost = AskCost(attempt, seconds=time.monotonic() - started)
            return Unanswered(Why.TIMED_OUT, f"no reply in {self.seconds:g} s", cost)
        return _answer(done, attempt, time.monotonic() - started)


def _answer(
    done: subprocess.CompletedProcess[str], attempt: int, seconds: float
) -> Reply | Unanswered:
    """The worker's line read: the reply with its tokens, the provider's error by its class and
    status, or the worker's end when it printed no line pyct can read."""
    try:
        said = json.loads(done.stdout)
    except json.JSONDecodeError:
        said = None
    cost = AskCost(attempt, seconds=seconds)
    if isinstance(said, dict) and isinstance(said.get("error"), str):
        status = said.get("status")
        reason = said["error"] if status is None else f"{said['error']} ({status})"
        return Unanswered(Why.PROVIDER, reason, cost)
    if isinstance(said, dict) and isinstance(said.get("text"), str):
        tokens_in, tokens_out = int(said.get("in", 0)), int(said.get("out", 0))
        return Reply(said["text"], AskCost(attempt, tokens_in, tokens_out, seconds))
    return Unanswered(Why.PROVIDER, f"the worker gave no reply (exit {done.returncode})", cost)
