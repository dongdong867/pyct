"""Acceptance tests for the track-a-value-through-a-loop-summary story through ``pyct run``: a
formula that passes its checks comes into use when each input runs in a process of its own, and
under ``--in-process`` the loop is not asked about and stderr says why.

Each run's base URLs point at a stub on localhost, and neither real key reaches pyct, so no
request leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import forks_of, input_lines, summary_line
from tests.acceptance.llm_stub import Stub, heads, llm_lines, llm_run
from tests.acceptance.llm_summaries import COUNT, G
from tests.acceptance.test_track_a_value_through_a_loop_summary import Z, holds, line_of

FEW_Z = "targets.summaries.loops::few_z"
SEED = '{"s": "ab"}'
ARGV = ("--llm", "summaries", "--plateau", "8")
SKIPPED = (
    f"llm: summary for the loop at {G}:{line_of('few_z', 'for c in s:')} skipped:"
    " inputs run in pyct's own process"
)


def state_of(stdout: str) -> object:
    """The state of the run's one loop in the summary line's ``llm.summaries``."""
    llm = summary_line(stdout)["llm"]
    assert isinstance(llm, dict)
    [item] = llm["summaries"]
    return item["state"]


def after_checked(stderr: str, stdout: str) -> list[dict[str, object]]:
    """The input lines of the inputs whose traces stderr holds after the ``checked on`` line."""
    lines = stderr.splitlines()
    checked = next(at for at, line in enumerate(lines) if ": checked on " in line)
    before = len(heads("\n".join(lines[:checked])))
    return input_lines(stdout)[before:]


# llm-summary-for-a-stuck-loop-not-used-in-pyct-s-own-process
def test_a_loop_is_not_asked_about_for_inputs_in_pyct_s_process_and_says_why(
    stub: Stub, tmp_path: Path
) -> None:
    # no formula could come into use, so the loop is not asked about
    # (refuse-a-summary-that-only-repeats-its-runs)
    stub.reply = COUNT

    result = llm_run(stub.port, tmp_path, SEED, *ARGV, "--in-process", target=FEW_Z)

    assert result.returncode == 0, result.stderr
    said = llm_lines(result.stderr)
    assert said.count(SKIPPED) == 1
    assert not any(": checked on " in line for line in said)
    test = line_of("few_z", 'if c == "z":')
    for line in input_lines(result.stdout):
        forks, args = forks_of(line), line["args"]
        assert isinstance(args, dict), line
        assert len([fork for fork in forks if fork["line"] == test]) == len(args["s"]), line
        assert not any(holds(fork["expression"], Z) for fork in forks), line
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert llm["summaries"] == []


def test_a_formula_for_inputs_in_a_process_of_their_own_comes_into_use(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply = COUNT

    result = llm_run(stub.port, tmp_path, SEED, *ARGV, target=FEW_Z)

    assert result.returncode == 0, result.stderr
    assert not any(" not used: " in line for line in llm_lines(result.stderr))
    assert state_of(result.stdout) == "in use"
    after = after_checked(result.stderr, result.stdout)
    assert after, result.stderr
    assert any(holds(fork["expression"], Z) for line in after for fork in forks_of(line))
