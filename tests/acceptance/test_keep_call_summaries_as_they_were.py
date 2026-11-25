"""Acceptance tests that lock the call summaries of the remove-loop-summaries ticket: what a call
summary asks and prints stays what it was at 21e4b3cc, the commit before loop summaries came out.

``call_summaries_at_21e4b3cc.json`` holds, for each case, the request text of each ask a run makes
through ``run_summaries``, and what a replay of the run's recording prints: its stderr lines that
start ``llm: summary for``, each input line without ``solver_seconds``, and the summary line's
``llm.summaries``. File paths are written relative to the repository root.

A run through ``pyct run`` has its base URLs pointed at a stub on localhost or at a closed port,
and no test calls a model.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.llm.summaries import request_text
from tests.acceptance.harness import REPO_ROOT, input_lines, summary_line, without_seconds
from tests.acceptance.llm_stub import Stub, closed_port, llm_lines, llm_run, recordings
from tests.acceptance.llm_summaries import (
    TOKENS,
    FakeSummaries,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import BOUNDED, DEDENTED, QUARTER, SHIFTED, WRONG

FIXTURE = Path(__file__).with_name("call_summaries_at_21e4b3cc.json")
PLATEAU = 20


@dataclass(frozen=True)
class Case:
    """A target, its seed, the reply the provider gives and the tokens it may spend."""

    name: str
    spec: str
    seed: dict[str, object]
    reply: str
    limit: int


# the formula of `SHIFTED` that comes into use and whose input runs again; a watched call in use;
# and a formula an input drops
CASES = (
    Case("shifted-in-use", SHIFTED, {"n": 3}, QUARTER, 100_000),
    Case(
        "watched-call-in-use",
        DEDENTED,
        {"s": "  ab"},
        code_reply('def summary(s):\n    return {"answer": s.strip()}'),
        100_000,
    ),
    Case("formula-dropped", BOUNDED, {"n": 2}, WRONG, sum(TOKENS)),
)


def relative(text: str) -> str:
    """``text`` with the repository's path taken off each file path in it."""
    return text.replace(f"{REPO_ROOT}/", "")


def expected(case: Case) -> dict[str, list[object]]:
    return json.loads(FIXTURE.read_text())[case.name]


def asked(case: Case) -> list[str]:
    """The request text of each ask a run of the case makes."""
    provider = FakeSummaries([case.reply], limit=case.limit)
    run_summaries(case.spec, case.seed, provider, Limits(plateau=Plateau(PLATEAU)))
    return [relative(request_text(request)) for request in provider.requests]


def replayed(case: Case, stub: Stub, tmp_path: Path) -> dict[str, list[object]]:
    """What a replay of the case's recording prints, after the recording is made through the
    stub and the replay is pointed at a closed port."""
    stub.reply = case.reply
    argv = (
        json.dumps(case.seed),
        "--llm",
        "summaries",
        "--plateau",
        str(PLATEAU),
        "--llm-limit",
        str(case.limit),
    )
    made = llm_run(stub.port, tmp_path, *argv, target=case.spec)
    assert made.returncode == 0, made.stderr
    [recording] = recordings(tmp_path)

    done = llm_run(closed_port(), tmp_path, *argv, "--llm-replay", str(recording), target=case.spec)

    assert done.returncode == 0, done.stderr
    llm = summary_line(done.stdout)["llm"]
    assert isinstance(llm, dict)
    return {
        "said": [
            relative(line) for line in llm_lines(done.stderr) if line.startswith("llm: summary for")
        ],
        "inputs": json.loads(
            relative(json.dumps([without_seconds(line) for line in input_lines(done.stdout)]))
        ),
        "summaries": json.loads(relative(json.dumps(llm["summaries"]))),
    }


# llm-summary-for-a-call-pyct-cannot-follow, the text of each ask
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_each_call_ask_s_text_is_as_it_was(case: Case) -> None:
    assert asked(case) == expected(case)["requests"]


# llm-summary-for-a-call-pyct-cannot-follow, the lines a replayed run prints
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_a_replayed_call_summary_prints_the_lines_it_printed(
    case: Case, stub: Stub, tmp_path: Path
) -> None:
    lines = replayed(case, stub, tmp_path)

    held = expected(case)
    assert {key: held[key] for key in lines} == lines
