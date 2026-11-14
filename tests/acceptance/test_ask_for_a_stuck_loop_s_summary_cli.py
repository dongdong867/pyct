"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``pyct run``:
``--llm summaries`` switches the tool on, alone or in ``all``, and the recording of each loop's
runs it switches on changes no input.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct
from tests.acceptance.llm_stub import Stub, closed_port, llm_lines, llm_run

COUNTS = "targets.why.stuck::counts"
SEED = '{"s": "ab"}'
PLATEAU = ("--plateau", "8")


# llm-switch-per-tool-summaries-alone
def test_llm_summaries_switches_on_summaries_alone(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", *PLATEAU, target=COUNTS)

    assert result.returncode == 0, result.stderr
    assert llm_lines(result.stderr)[0].endswith("tools: summaries")
    assert not any("Suggest seeds" in str(each.body) for each in stub.received)


# llm-switch-per-tool-all-holds-summaries
def test_llm_all_holds_summaries_after_seeds_and_before_rewrites(
    stub: Stub, tmp_path: Path
) -> None:
    result = llm_run(stub.port, tmp_path, SEED, "--llm", "all", *PLATEAU, target=COUNTS)

    assert result.returncode == 0, result.stderr
    assert (
        llm_lines(result.stderr)[0] == "llm: openai:gpt-6-luna, tools: seeds, summaries, rewrites"
    )


# llm-summary-for-a-stuck-loop-recording-changes-no-input
def test_the_recording_summaries_switches_on_changes_no_input(tmp_path: Path) -> None:
    asked = llm_run(closed_port(), tmp_path, SEED, "--llm", "summaries", *PLATEAU, target=COUNTS)
    plain = run_pyct(COUNTS, SEED, *PLATEAU)

    assert asked.returncode == 0, asked.stderr
    assert plain.returncode == 0, plain.stderr
    # the moment came, and its ask failed
    assert any(line.startswith("llm: summaries ask skipped: ") for line in llm_lines(asked.stderr))

    def inputs(stdout: str) -> list[tuple[object, object, object]]:
        return [(line["args"], line["covered"], line["forks"]) for line in input_lines(stdout)]

    assert inputs(asked.stdout) == inputs(plain.stdout)
    assert len(input_lines(plain.stdout)) > 1
