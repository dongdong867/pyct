"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``pyct run``:
``--llm summaries`` switches the tool on, alone or in ``all``, the recording of each loop's runs
it switches on changes no input, and the summary line lists each loop asked about with its state.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.llm_stub import Stub, closed_port, llm_lines, llm_run
from tests.acceptance.llm_summaries import COUNT, F, code_reply

COUNTS = "targets.why.stuck::counts"
SEED = '{"s": "ab"}'
PLATEAU = ("--plateau", "8")
FORMULA = 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'
LENGTH = 'def summary(s, t):\n    return {"t": len(s)}'


def summaries_of(stdout: str) -> object:
    """The summary line's ``llm.summaries``."""
    llm = summary_line(stdout)["llm"]
    assert isinstance(llm, dict)
    return llm["summaries"]


def loop_item(formula: str, state: str, checked_on: int | None) -> dict[str, object]:
    """``counts``'s loop as ``llm.summaries`` lists it after its one try."""
    return {
        "kind": "loop",
        "file": F,
        "line": 10,
        "col": 4,
        "changes": ["t"],
        "formula": formula,
        "condition": None,
        "state": state,
        "tries": 1,
        "checked_on": checked_on,
    }


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


# llm-summary-for-a-stuck-loop-state-in-the-summary-line
def test_the_summary_line_lists_a_checked_loop_with_its_formula(stub: Stub, tmp_path: Path) -> None:
    stub.reply = COUNT

    result = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", *PLATEAU, target=COUNTS)

    assert result.returncode == 0, result.stderr
    [checked] = [line for line in llm_lines(result.stderr) if "checked on" in line]
    runs = int(checked.split("checked on ")[1].split()[0])
    assert summaries_of(result.stdout) == [loop_item(FORMULA, "checked", runs)]
    # the file as the coverage map names it
    covered = summary_line(result.stdout)["covered"]
    assert isinstance(covered, dict) and F in covered


# llm-summary-for-a-stuck-loop-state-in-the-summary-line
def test_the_summary_line_lists_a_loop_whose_last_try_failed(stub: Stub, tmp_path: Path) -> None:
    stub.reply = code_reply(LENGTH)

    result = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", *PLATEAU, target=COUNTS)

    assert result.returncode == 0, result.stderr
    assert summaries_of(result.stdout) == [loop_item(f"{LENGTH}\n", "failed", None)]


# llm-summary-for-a-stuck-loop-state-in-the-summary-line
def test_a_run_that_asked_about_no_loop_lists_none(stub: Stub, tmp_path: Path) -> None:
    stub.reply = "[]"

    # `f` has no loop, and its inputs cover every line
    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "summaries", *PLATEAU)

    assert result.returncode == 0, result.stderr
    assert stub.received == []
    assert summaries_of(result.stdout) == []
