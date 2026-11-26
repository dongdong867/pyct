"""Acceptance tests for the remove-loop-summaries story: with summaries switched on, pyct asks
nothing about a loop, prints no ``llm: summary for the loop`` line, and lists no loop in the
summary line's ``llm.summaries``, also when a recording holds a reply about one.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

import pytest

from tests.acceptance.harness import input_lines, run_pyct, summary_line, without_seconds
from tests.acceptance.llm_stub import Stub, closed_port, llm_lines, llm_run, write_recording
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTS,
    SEED,
    FakeSummaries,
    one_thread,  # noqa: F401
    run_summaries,
)

ARGS = '{"s": "ab"}'
PLATEAU = ("--plateau", "8")
LOOP_LINE = "llm: summary for the loop"


def llm_of(stdout: str) -> dict[str, object]:
    """The summary line's ``llm`` entry."""
    llm = summary_line(stdout)["llm"]
    assert isinstance(llm, dict)
    return llm


# llm-summary-for-a-stuck-loop, removed: no ask about a loop
def test_a_run_with_summaries_sends_no_ask_about_a_loop() -> None:
    provider = FakeSummaries([COUNT])

    ran = run_summaries(COUNTS, SEED, provider)

    assert provider.requests == []
    assert not any(line.startswith(LOOP_LINE) for line in ran.said)
    assert ran.result.summaries == ()


# llm-summary-for-a-stuck-loop, removed: no loop line, and no loop in the summary line
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_pyct_run_prints_no_loop_summary_line_and_lists_no_loop(
    where: tuple[str, ...], stub: Stub, tmp_path: Path
) -> None:
    stub.reply = COUNT

    result = llm_run(
        stub.port, tmp_path, ARGS, "--llm", "summaries", *PLATEAU, *where, target=COUNTS
    )

    assert result.returncode == 0, result.stderr
    assert not any(line.startswith(LOOP_LINE) for line in llm_lines(result.stderr))
    assert llm_of(result.stdout)["summaries"] == []
    assert stub.received == []


# llm-summary-for-a-stuck-loop, removed: a recorded reply about a loop is left unused
def test_a_recording_that_holds_a_loop_s_reply_replays_without_it(tmp_path: Path) -> None:
    reply = {"tool": "summaries", "place": "targets.why.stuck:10:4", "try": 1, "reply": COUNT}
    recording = write_recording(tmp_path / "loop.jsonl", [reply])
    replay = ("--llm", "summaries", "--llm-replay", str(recording), *PLATEAU)

    replayed = llm_run(closed_port(), tmp_path, ARGS, *replay, target=COUNTS)
    plain = run_pyct(COUNTS, ARGS, *PLATEAU)

    assert replayed.returncode == 0, replayed.stderr
    assert plain.returncode == 0, plain.stderr
    assert not any(line.startswith(LOOP_LINE) for line in llm_lines(replayed.stderr))
    assert llm_of(replayed.stdout)["replayed"] == 0

    def inputs(stdout: str) -> list[dict[str, object]]:
        return [without_seconds(line) for line in input_lines(stdout)]

    assert inputs(replayed.stdout) == inputs(plain.stdout)
