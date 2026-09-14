"""Acceptance tests for the finish-a-run story, child print-the-summary-line.

Each test spawns ``python -P -m pyct`` through the harness, the way the flip-one-fork
tests do: the summary line closes stdout after the last input line, so only a real run
through the command line proves the order it comes in and the environment it names.
"""

import platform

from tests.acceptance.harness import input_lines, run_pyct, summary_line

ONE_CHECK = "targets.flip.one_check::classify"


def covered_of(line: dict[str, object]) -> dict[str, set[int]]:
    """The covered map off a printed line, as sets, so the union means something."""
    payload = line["covered"]
    assert isinstance(payload, dict), line
    return {str(file): {int(number) for number in lines} for file, lines in payload.items()}


def union_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        for file, covered in covered_of(line).items():
            union[file] = union.get(file, set()) | covered
    return {file: sorted(covered) for file, covered in union.items()}


# finish-a-run-prints-the-summary-line
def test_prints_the_summary_line() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    summary = summary_line(result.stdout)
    # summary_line takes the last line and asserts the key; no input line carries it
    assert all("stopped" not in line for line in inputs), result.stdout
    assert len(inputs) == 2, result.stdout
    assert summary["inputs"] == len(inputs)
    # the run's coverage is every input's added up, and the module is the same size throughout
    assert summary["covered"] == union_of(inputs)
    assert all(line["total"] == summary["total"] for line in inputs), result.stdout
    environment = summary["environment"]
    assert isinstance(environment, dict), summary
    # the harness spawns this interpreter, so the version and the platform are this process's
    assert environment["python"] == platform.python_version()
    assert environment["platform"] == platform.platform()
    cvc5 = environment["cvc5"]
    assert isinstance(cvc5, str) and cvc5, summary


def counts_of(summary: dict[str, object], key: str) -> dict[str, object]:
    """One map off the summary line, narrowed so a lookup on it means something."""
    payload = summary[key]
    assert isinstance(payload, dict), summary
    return payload


def after_the_last_trace(stderr: str) -> list[str]:
    """The stderr lines that sum the run, past the last input's own trace.

    Every input's trace ends on its ``downgrades`` line, so the last one is
    where the run's summary starts.
    """
    lines = stderr.splitlines()
    last = max(at for at, line in enumerate(lines) if line.startswith("downgrades "))
    return lines[last + 1 :]


# finish-a-run-writes-the-summary-to-stderr
def test_writes_the_summary_to_stderr() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    covered = counts_of(summary, "covered")
    total = counts_of(summary, "total")
    (file,) = covered
    summed = after_the_last_trace(result.stderr)
    # the words are the per-input trace's, over the run's own counts
    assert summed[0] == f"covered {len(covered[file])} of {total[file]} lines in {file}"
    assert summed[1] == "solver: 1 sat, 0 unsat, 0 unknown, 0 timeout"
    assert summed[-1].startswith("stopped: "), result.stderr
