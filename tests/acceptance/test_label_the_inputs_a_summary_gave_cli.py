"""Acceptance test for the label-the-inputs-a-summary-gave story through ``pyct run``: a run whose
seed leaves no fork to flip runs the seed again once its formula is in use, and the solver input
aimed at the formula's count says ``"source": "summary"``.

The run's base URLs point at a stub on localhost, and neither real key reaches pyct, so no request
leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import input_lines, summary_line
from tests.acceptance.llm_stub import Stub, heads, llm_run
from tests.acceptance.llm_summaries import COUNT
from tests.acceptance.test_track_a_value_through_a_loop_summary import line_of

ENCODED_Z = "targets.summaries.loops::encoded_z"


# llm-summary-input-cli
def test_a_no_fork_run_goes_on_with_inputs_labeled_summary(stub: Stub, tmp_path: Path) -> None:
    stub.reply = COUNT

    result = llm_run(stub.port, tmp_path, '{"s": "ab"}', "--llm", "summaries", target=ENCODED_Z)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert [line["source"] for line in lines[:2]] == ["seed", "summary"], result.stdout
    assert (lines[1]["args"], lines[1]["aim"]) == ({"s": "ab"}, None)
    test = line_of("encoded_z", "if t > 3:")
    aimed = [
        line for line in lines[2:] if isinstance(aim := line["aim"], dict) and aim["line"] == test
    ]
    assert [line["source"] for line in aimed[:1]] == ["summary"], result.stdout
    inputs = summary_line(result.stdout)["inputs"]
    assert isinstance(inputs, int) and inputs > 1
    assert heads(result.stderr)[1].startswith("summary ")
