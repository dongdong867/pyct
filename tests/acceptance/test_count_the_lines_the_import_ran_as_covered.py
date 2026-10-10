"""Acceptance tests for the count-the-lines-the-import-ran-as-covered story.

Each test spawns ``python -P -m pyct`` through the harness, or ``pyct sweep``, and reads the
summary line, the input lines and stderr as a person or a tool reads them after a run.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    input_lines,
    numbers_of,
    one_line,
    run_pyct,
    summary_line,
)
from tests.acceptance.sweeping import FIXTURES, row_named, sweep
from tests.acceptance.sweeping import summary as sweep_summary


def spec(module: str) -> tuple[str, str]:
    """A target ``f`` under ``targets/why``: what the command line names, and F, its file."""
    return f"targets.why.{module}::f", str(REPO_ROOT / "targets" / "why" / f"{module}.py")


# line 1 `import pickle`, line 3 `def f(x):`, line 4 `return x`, line 7 `LIMIT = 10`
AT_IMPORT, AT_IMPORT_FILE = spec("at_import")
# line 4 `if __name__ == "__main__":`, line 5 under it
MAIN_GUARD, MAIN_GUARD_FILE = spec("main_guard")
# line 5 calls `helper(False)`, whose line 3 only a true flag runs
CALLED_AT_IMPORT, CALLED_AT_IMPORT_FILE = spec("called_at_import")
# line 3 calls `helper(0)`, which runs line 2; `f` calls it only for x above 0
PLATEAU_AT_IMPORT, PLATEAU_AT_IMPORT_FILE = spec("plateau_at_import")
# line 2 raises, line 4 `LIMIT = 10`
RAISES_AT_CALL, RAISES_AT_CALL_FILE = spec("raises_at_call")
SEED = '{"x": 0}'


def covered_lines(line: dict[str, object], file: str) -> set[int]:
    """The lines one stdout line covers in ``file``."""
    return set(numbers_of(line, "covered").get(file, []))


# count-the-lines-the-import-ran-as-covered-covers-the-def-line
def test_covers_the_def_line() -> None:
    result = run_pyct(AT_IMPORT, SEED)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert numbers_of(summary, "covered") == {AT_IMPORT_FILE: [1, 3, 4, 7]}
    assert summary["total"] == {AT_IMPORT_FILE: 4}
    assert numbers_of(summary, "uncovered") == {AT_IMPORT_FILE: []}
    assert summary["why_uncovered"] == []
    after_trace = result.stderr.splitlines()[-3:]
    assert after_trace[0] == f"covered 4 of 4 lines in {AT_IMPORT_FILE}", result.stderr
    assert not any(line.startswith("uncovered ") for line in after_trace), result.stderr


# count-the-lines-the-import-ran-as-covered-keeps-each-input-s-own-lines
def test_keeps_each_input_s_own_lines() -> None:
    result = run_pyct(AT_IMPORT, SEED)

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert numbers_of(seed, "covered") == {AT_IMPORT_FILE: [4]}
    assert seed["total"] == {AT_IMPORT_FILE: 4}
    trace = result.stderr.splitlines()
    assert trace[1] == f"covered 1 of 4 lines in {AT_IMPORT_FILE}", result.stderr


# count-the-lines-the-import-ran-as-covered-leaves-a-line-the-import-skipped
def test_leaves_a_line_the_import_skipped() -> None:
    result = run_pyct(MAIN_GUARD, SEED)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    covered = covered_lines(summary, MAIN_GUARD_FILE)
    assert 4 in covered
    assert 5 not in covered
    assert summary["why_uncovered"] == [{"file": MAIN_GUARD_FILE, "lines": [5], "reason": "import"}]


# count-the-lines-the-import-ran-as-covered-counts-a-function-the-import-called
def test_counts_a_function_the_import_called() -> None:
    result = run_pyct(CALLED_AT_IMPORT, SEED)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert numbers_of(summary, "covered") == {CALLED_AT_IMPORT_FILE: [1, 2, 4, 5, 6, 7]}
    # no input entered helper, so its line the import skipped is not called, not the import's
    assert summary["why_uncovered"] == [
        {"file": CALLED_AT_IMPORT_FILE, "lines": [3], "reason": "not called", "function": "helper"}
    ]


# count-the-lines-the-import-ran-as-covered-keeps-the-plateau-on-input-lines
def test_keeps_the_plateau_on_input_lines() -> None:
    result = run_pyct(PLATEAU_AT_IMPORT, SEED, "--plateau", "1")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 3, result.stdout
    seed, second, third = (covered_lines(line, PLATEAU_AT_IMPORT_FILE) for line in inputs)
    # line 2 is new to the inputs, though the import ran it, so the plateau of 1 does not stop
    assert second - seed == {2}
    assert 7 in third
    summary = summary_line(result.stdout)
    assert 2 in covered_lines(summary, PLATEAU_AT_IMPORT_FILE)
    assert summary["stopped"] == "no fork to flip"


# count-the-lines-the-import-ran-as-covered-counts-them-in-process
def test_counts_them_in_process() -> None:
    isolated = run_pyct(AT_IMPORT, SEED)
    in_process = run_pyct(AT_IMPORT, SEED, "--in-process")

    assert isolated.returncode == 0, isolated.stderr
    assert in_process.returncode == 0, in_process.stderr
    for result in (isolated, in_process):
        summary = summary_line(result.stdout)
        assert numbers_of(summary, "covered") == {AT_IMPORT_FILE: [1, 3, 4, 7]}, result.stdout


# count-the-lines-the-import-ran-as-covered-adds-them-to-a-sweep
def test_adds_them_to_a_sweep() -> None:
    pair = f"{FIXTURES}.pair"
    path = str(REPO_ROOT / "targets" / "sweep" / "pair.py")
    # `def first` and `def second`, which only the import runs
    def_lines = {5, 11}

    result = sweep(pair)

    assert result.returncode == 0, result.stderr
    totals = sweep_summary(result.stdout)
    assert def_lines <= set(totals["covered"][path]), totals
    for name in ("first", "second"):
        row = row_named(result.stdout, pair, name)
        run = row["run"]
        assert def_lines <= set(run["covered"][path]), row
        lines = sum(len(lines) for lines in run["covered"].values())
        told = f"ran {pair}::{name}: covered {lines} of {run['total'][path]} lines"
        assert any(line.startswith(told) for line in result.stderr.splitlines()), result.stderr


# count-the-lines-the-import-ran-as-covered-keeps-them-when-the-seed-raises
def test_keeps_them_when_the_seed_raises() -> None:
    result = run_pyct(RAISES_AT_CALL, SEED)

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    failure = seed["failure"]
    assert isinstance(failure, dict), seed
    assert failure["kind"] == "target_raised"
    assert numbers_of(seed, "covered") == {RAISES_AT_CALL_FILE: [2]}
    summary = summary_line(result.stdout)
    assert numbers_of(summary, "covered") == {RAISES_AT_CALL_FILE: [1, 2, 4]}
    assert numbers_of(summary, "uncovered") == {RAISES_AT_CALL_FILE: []}
