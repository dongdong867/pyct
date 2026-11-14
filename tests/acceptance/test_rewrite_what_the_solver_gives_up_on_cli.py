"""Acceptance tests for the rewrite-what-the-solver-gives-up-on story through ``pyct run``:
``--llm rewrites`` switches the tool on alone, the budget's clock pauses while the model answers,
and a recorded run replays with no model called.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine; the worker and the adapter run
for real, and each rewrite runs in a child forked from pyct's process.
"""

from pathlib import Path

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, summary_line
from tests.acceptance.llm_stub import (
    Stub,
    closed_port,
    llm_lines,
    llm_run,
    read_recording,
    recordings,
)

TEXT = "targets.rewrites.text::exponent"
F = str(REPO_ROOT / "targets" / "rewrites" / "text.py")
AT = f"llm: rewrite for {F}:2:7"
SEED = '{"s": "0"}'
SHORT = ("--solver-timeout", "1")


def rewritten(stdout: str) -> list[dict[str, object]]:
    return [line for line in input_lines(stdout) if line["source"] == "rewrite"]


# llm-rewrite-switch-alone
def test_llm_rewrites_asks_for_a_rewrite_and_runs_its_input(stub: Stub, tmp_path: Path) -> None:
    stub.reply = 's == "1e-30"'

    result = llm_run(stub.port, tmp_path, SEED, "--llm", "rewrites", *SHORT, target=TEXT)

    assert result.returncode == 0, result.stderr
    lines = llm_lines(result.stderr)
    assert lines[0] == "llm: openai:gpt-6-luna, tools: rewrites"
    assert [line for line in lines if line.startswith(AT)] == [
        f'{AT}: s == "1e-30"',
        f"{AT}: took the wanted side",
    ]
    assert not any(line.startswith("llm: summary") for line in lines)
    [found] = rewritten(result.stdout)
    assert found["args"] == {"s": "1e-30"}
    assert found["aim"] == {"file": F, "line": 2, "col": 7, "position": 1}
    assert 3 in summary_line(result.stdout)["covered"][F]  # pyrefly: ignore[bad-index]


def test_llm_seeds_alone_asks_for_no_rewrite(stub: Stub, tmp_path: Path) -> None:
    stub.reply = "[]"

    seeds = llm_run(stub.port, tmp_path, SEED, "--llm", "seeds", *SHORT, target=TEXT)

    assert seeds.returncode == 0, seeds.stderr
    [asked] = stub.received
    assert "Rewrite it as" not in str(asked.body)
    assert not any(line.startswith("llm: rewrite") for line in llm_lines(seeds.stderr))
    assert rewritten(seeds.stdout) == []


# llm-rewrite-switch-not-in-summaries
def test_llm_summaries_alone_asks_for_no_rewrite(stub: Stub, tmp_path: Path) -> None:
    stub.reply = "[]"

    summaries = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", *SHORT, target=TEXT)

    assert summaries.returncode == 0, summaries.stderr
    assert not any("Rewrite it as" in str(each.body) for each in stub.received)
    assert not any(line.startswith("llm: rewrite") for line in llm_lines(summaries.stderr))
    assert rewritten(summaries.stdout) == []


# llm-rewrite-when-the-solver-gives-up-pauses-the-budget-while-waiting
@pytest.mark.serial
def test_the_summary_counts_the_seconds_waited_past_the_budget(stub: Stub, tmp_path: Path) -> None:
    stub.reply = 's == "1e-30"'
    stub.delay = 12.0

    result = llm_run(
        stub.port, tmp_path, SEED, "--llm", "rewrites", "--budget", "10", *SHORT, target=TEXT
    )

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert summary["stopped"] != "budget spent"
    assert len(rewritten(result.stdout)) == 1
    llm = summary["llm"]
    assert isinstance(llm, dict)
    assert 12.0 <= llm["seconds"] < 20.0  # pyrefly: ignore[unsupported-operation]


# llm-rewrite-input-says-rewrite, through a replay of a recorded run
def test_a_recorded_rewrites_run_replays_with_no_model(stub: Stub, tmp_path: Path) -> None:
    stub.reply = 's == "1e-30"'
    llm_run(stub.port, tmp_path, SEED, "--llm", "rewrites", *SHORT, target=TEXT)
    [recording] = recordings(tmp_path)
    [_, reply] = read_recording(recording)
    assert (reply["tool"], reply["place"], reply["try"]) == (
        "rewrites",
        "targets.rewrites.text:2:7",
        1,
    )

    replayed = llm_run(
        closed_port(),
        tmp_path,
        SEED,
        "--llm",
        "rewrites",
        "--llm-replay",
        str(recording),
        *SHORT,
        target=TEXT,
    )

    assert replayed.returncode == 0, replayed.stderr
    assert len(stub.received) == 1
    [found] = rewritten(replayed.stdout)
    assert found["args"] == {"s": "1e-30"}
    llm = summary_line(replayed.stdout)["llm"]
    assert isinstance(llm, dict)
    assert (llm["model"], llm["asks"], llm["replayed"]) == ("openai:gpt-6-luna", 0, 1)


def test_a_rewrite_s_ask_is_dumped_beside_the_run_s_own(stub: Stub, tmp_path: Path) -> None:
    stub.reply = 's == "1e-30"'
    dumped = tmp_path / "asks"

    result = llm_run(
        stub.port,
        tmp_path,
        SEED,
        "--llm",
        "rewrites",
        "--dump-formulas",
        str(dumped),
        *SHORT,
        target=TEXT,
    )

    assert result.returncode == 0, result.stderr
    files = sorted(dumped.iterdir())
    numbers = {int(path.stem.split("-")[1]) for path in files}
    # each ask numbered once among the run's, from 1, with no gap
    assert numbers == set(range(1, len(numbers) + 1))
    programs = [path.read_text() for path in files]
    # the run's own ask reads float(s); the rewrite's compares s to the string itself
    assert any('"1e-30"' in program for program in programs)
    assert any('"1e-30"' not in program for program in programs)
