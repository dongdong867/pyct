"""Acceptance tests for the trace-the-seed story, child run-the-seed-and-print-the-line.

Every test spawns ``python -P -m pyct`` in a subprocess from the repository root with
``PYTHONPATH`` removed. The current-directory criterion cannot be proven in-process,
and the import-path edit ``load_target`` makes would leak between in-process tests.
``-P`` is what makes that criterion mean anything: without it ``-m`` puts the working
directory on ``sys.path`` itself, so the target would import even if ``load_target``
never touched the path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = "targets.trace.uncalled_helper::classify"
TARGET_FILE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
TWO_CHECKS = "targets.trace.two_checks::bucket"
TWO_CHECKS_FILE = str(REPO_ROOT / "targets" / "trace" / "two_checks.py")
CALLS_HELPER = "targets.trace.calls_helper::route"
CALLS_HELPER_FILE = str(REPO_ROOT / "targets" / "trace" / "calls_helper.py")
HELPER_CHECK_FILE = str(REPO_ROOT / "targets" / "trace" / "helper_check.py")


def run_pyct(*argv: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def one_line(stdout: str) -> dict[str, object]:
    lines = stdout.splitlines()
    assert len(lines) == 1, stdout
    return json.loads(lines[0])


# trace-the-seed-prints-one-json-line
def test_prints_one_json_line_with_the_forks() -> None:
    result = run_pyct(TARGET, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["args"] == {"x": 3}
    # the one fork the seed hit: `x < 10` on line 5, column 7, taken
    assert line["forks"] == [
        {
            "file": TARGET_FILE,
            "line": 5,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 10],
        }
    ]
    assert line["covered"] == {TARGET_FILE: [5, 6]}
    assert line["total"] == {TARGET_FILE: 7}
    assert line.get("failure") is None
    assert not line.get("downgrades")


# trace-the-seed-lists-forks-in-order
def test_lists_forks_in_order() -> None:
    result = run_pyct(TWO_CHECKS, '{"x": 5}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    # the seed passes both checks, so both forks are hit, in the order the target tests them
    assert line["forks"] == [
        {
            "file": TWO_CHECKS_FILE,
            "line": 3,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 10],
        },
        {
            "file": TWO_CHECKS_FILE,
            "line": 5,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 100],
        },
    ]
    # every line but the def, which ran at import
    assert line["covered"] == {TWO_CHECKS_FILE: [2, 3, 4, 5, 6, 7]}
    assert line["total"] == {TWO_CHECKS_FILE: 7}


# trace-the-seed-lists-a-fork-in-another-module
def test_lists_a_fork_in_another_module() -> None:
    result = run_pyct(CALLS_HELPER, '{"x": 200}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    # the target's own `x < 100` first, then the helper's `x < 5` in the helper's own
    # file: the order they ran, not the order of their files
    assert line["forks"] == [
        {
            "file": CALLS_HELPER_FILE,
            "line": 5,
            "col": 7,
            "taken": False,
            "expression": ["<", "x", 100],
        },
        {
            "file": HELPER_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": ["<", "x", 5],
        },
    ]
    # the fork's file does not join the coverage maps: they stay on the target's module
    assert line["covered"] == {CALLS_HELPER_FILE: [5, 7, 9]}
    assert line["total"] == {CALLS_HELPER_FILE: 7}


# trace-the-seed-imports-from-the-current-directory
def test_imports_from_the_current_directory() -> None:
    result = run_pyct(TARGET, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["args"] == {"x": 1}


# trace-the-seed-counts-lines-against-the-module
def test_counts_lines_against_the_module() -> None:
    result = run_pyct(TARGET, '{"x": 1}')

    line = one_line(result.stdout)
    # docstring, two def lines, four body lines; never_called's body is in the total
    assert line["total"] == {TARGET_FILE: 7}
    # only the two lines the seed ran: the if and its return
    assert line["covered"] == {TARGET_FILE: [5, 6]}


# trace-the-seed-refuses-missing-args
def test_refuses_missing_args() -> None:
    result = run_pyct(TARGET)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "required" in result.stderr
    assert "x" in result.stderr.split("required", 1)[1]
    assert "--args" in result.stderr


# trace-the-seed-refuses-malformed-args
def test_refuses_malformed_args() -> None:
    for bad in ["[1, 2]", "not json", '"x"']:
        result = run_pyct(TARGET, bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        assert "JSON object" in result.stderr, bad


# deviation in the trace-the-seed build log: a seed whose keys do not fit is a usage error
def test_refuses_a_seed_that_does_not_fit_the_parameters() -> None:
    for bad, named in {'{"y": 1}': "y", "{}": "x"}.items():
        result = run_pyct(TARGET, bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        assert named in result.stderr, bad
        assert "Traceback" not in result.stderr, bad


# trace-the-seed-refuses-bad-target-form
def test_refuses_bad_target_form() -> None:
    for bad in ["targets.trace.uncalled_helper", "targets/trace/uncalled_helper.py::classify"]:
        result = run_pyct(bad, '{"x": 1}')

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        assert "MODULE::FUNCTION" in result.stderr, bad


# trace-the-seed-fails-when-target-not-importable
def test_fails_when_target_not_importable() -> None:
    cases = {
        "targets.trace.broken_import::anything": "targets.trace.broken_import",
        "targets.trace.no_such_module::f": "targets.trace.no_such_module",
        "targets.trace.uncalled_helper::no_such_function": "no_such_function",
    }
    for spec, named in cases.items():
        result = run_pyct(spec, '{"x": 1}')

        assert result.returncode == 1, spec
        assert result.stdout == "", spec
        assert named in result.stderr, spec


# deviation in the trace-the-seed build log: a module with no Python source is refused
def test_fails_when_target_has_no_python_source() -> None:
    # math imports and has the function on every CPython, but never has a .py file
    result = run_pyct("math::sqrt", '{"x": 4}')

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["math has no Python source file"]
