"""Acceptance tests for part E of the match-pyct-v1-on-the-measured-functions story.

Each input's trace names the lines that input covered first, after its ``covered`` line. The
tests spawn ``python -P -m pyct`` through the harness and read stderr as a person reads it.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, numbers_of, run_pyct

# line 1 the def the import runs; lines 2, 3, 7 and 9 an empty string runs; line 8
# `return "medium"`
COUNT_Z = "targets.stop.count_z::test"
COUNT_Z_FILE = str(REPO_ROOT / "targets" / "stop" / "count_z.py")


def blocks(stderr: str) -> list[list[str]]:
    """Each input's trace, one list of lines per input, in run order."""
    traces: list[list[str]] = []
    for line in stderr.splitlines():
        if line.startswith(("seed {", "solver {")):
            traces.append([])
        if traces and not line.startswith("missed "):
            traces[-1].append(line)
    return traces


def first_covered(trace: list[str]) -> list[str]:
    """The trace's `first covered` lines, each checked to follow its `covered` line."""
    found = [i for i, line in enumerate(trace) if line.startswith("first covered ")]
    for i in found:
        assert trace[i - 1].startswith("covered "), trace
    return [trace[i] for i in found]


# match-pyct-v1-on-the-measured-functions-trace-names-new-lines
def test_each_trace_names_the_lines_its_input_covered_first() -> None:
    result = run_pyct(COUNT_Z, '{"s": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    traces = blocks(result.stderr)
    inputs = input_lines(result.stdout)
    assert len(traces) == len(inputs)
    # the seed's names the lines it ran, less the def line the import ran
    assert first_covered(traces[0]) == [f"first covered 2, 3, 7, 9 in {COUNT_Z_FILE}"]
    medium = next(
        i for i, line in enumerate(inputs) if 8 in numbers_of(line, "covered")[COUNT_Z_FILE]
    )
    assert first_covered(traces[medium]) == [f"first covered 8 in {COUNT_Z_FILE}"]
    seen: set[int] = {1}
    quiet = 0
    for trace, line in zip(traces, inputs, strict=True):
        covered = set(numbers_of(line, "covered")[COUNT_Z_FILE])
        if covered <= seen:
            assert first_covered(trace) == [], trace
            quiet += 1
        seen |= covered
    assert quiet > 0
