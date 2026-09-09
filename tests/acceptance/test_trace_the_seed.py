"""Acceptance tests for the trace-the-seed story, child run-the-seed-and-print-the-line.

Every test but the pyct-bug one spawns ``python -P -m pyct`` in a subprocess from the
repository root with ``PYTHONPATH`` removed. The current-directory criterion cannot be
proven in-process, and the import-path edit ``load_target`` makes would leak between
in-process tests. ``-P`` is what makes that criterion mean anything: without it ``-m``
puts the working directory on ``sys.path`` itself, so the target would import even if
``load_target`` never touched the path. The pyct-bug test is in-process because a pyct
bug can only be provoked by patching pyct itself.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyct.cli import main
from pyct.core import values
from pyct.core.branch import Site

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = "targets.trace.uncalled_helper::classify"
TARGET_FILE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
TWO_CHECKS = "targets.trace.two_checks::bucket"
TWO_CHECKS_FILE = str(REPO_ROOT / "targets" / "trace" / "two_checks.py")
CALLS_HELPER = "targets.trace.calls_helper::route"
CALLS_HELPER_FILE = str(REPO_ROOT / "targets" / "trace" / "calls_helper.py")
HELPER_CHECK_FILE = str(REPO_ROOT / "targets" / "trace" / "helper_check.py")
RAISES = "targets.trace.raises::explode"
RAISES_FILE = str(REPO_ROOT / "targets" / "trace" / "raises.py")
EXITS = "targets.trace.exits::leave"
EXITS_FILE = str(REPO_ROOT / "targets" / "trace" / "exits.py")
NEVER_RETURNS = "targets.trace.never_returns::spin"
NEVER_RETURNS_FILE = str(REPO_ROOT / "targets" / "trace" / "never_returns.py")
THROUGH_ABS = "targets.trace.through_abs::size"
THROUGH_ABS_FILE = str(REPO_ROOT / "targets" / "trace" / "through_abs.py")


def run_pyct(*argv: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # the timeout test spawns a target that never returns, so a broken
        # budget has to fail the test instead of hanging the suite
        timeout=30,
    )


def let_pyct_run_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put this interpreter where a fresh one would be, and undo it after the test.

    ``load_target`` inserts the working directory on ``sys.path`` and leaves the
    imported target in ``sys.modules``; both are restored so the subprocess tests
    around this one keep proving what they prove.
    """
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in [n for n in sys.modules if n.split(".", 1)[0] == "targets"]:
        monkeypatch.delitem(sys.modules, name)


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
    assert line["failure"] is None
    assert line["downgrades"] == []


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
    result = run_pyct(CALLS_HELPER, '{"x": 50}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    # the helper's `x < 5` in the helper's own file first, then the target's own `x < 100`:
    # the order they ran, which is the reverse of the order their files sort in
    assert line["forks"] == [
        {
            "file": HELPER_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": ["<", "x", 5],
        },
        {
            "file": CALLS_HELPER_FILE,
            "line": 7,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 100],
        },
    ]
    # the fork's file does not join the coverage maps: they stay on the target's module
    assert line["covered"] == {CALLS_HELPER_FILE: [5, 7, 8]}
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


# trace-the-seed-reports-a-raise
def test_reports_a_raise() -> None:
    result = run_pyct(RAISES, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["failure"] == {"kind": "target_raised", "detail": "ValueError: too small"}
    # the fork before the raise is kept, and the lines up to the raise
    assert line["forks"] == [
        {"file": RAISES_FILE, "line": 2, "col": 7, "taken": True, "expression": ["<", "x", 10]}
    ]
    assert line["covered"] == {RAISES_FILE: [2, 3]}
    assert line["total"] == {RAISES_FILE: 4}
    assert line["downgrades"] == []


# trace-the-seed-reports-a-system-exit
def test_reports_a_system_exit() -> None:
    result = run_pyct(EXITS, '{"x": 3}')

    # pyct keeps going: the line is printed and the exit is pyct's own, not the target's 3
    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["failure"] == {"kind": "system_exit", "detail": "SystemExit: 3"}
    assert line["covered"] == {EXITS_FILE: [5, 6]}
    # the import, the def, and the three body lines
    assert line["total"] == {EXITS_FILE: 5}


# trace-the-seed-reports-a-timeout
def test_reports_a_timeout() -> None:
    result = run_pyct(NEVER_RETURNS, '{"x": 1}', "--budget", "1")

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    failure = line["failure"]
    assert isinstance(failure, dict)
    assert failure["kind"] == "timeout"
    assert isinstance(failure["detail"], str)
    assert failure["detail"] != ""
    # the three lines the loop reached before the deadline
    assert line["covered"] == {NEVER_RETURNS_FILE: [2, 3, 4]}
    # the def and the three body lines; the compiler drops `return n` after `while True`
    assert line["total"] == {NEVER_RETURNS_FILE: 4}


# README › Rules › the budget
def test_refuses_a_budget_that_is_not_a_positive_number() -> None:
    for bad in ["0", "-1", "abc"]:
        result = run_pyct(TARGET, '{"x": 1}', "--budget", bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        assert "budget" in result.stderr, bad


# trace-the-seed-fails-on-a-pyct-bug
def test_fails_on_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> Site:
        raise RuntimeError("boom")

    let_pyct_run_in_process(monkeypatch)
    # the target's `x < 10` reaches this through pyct's own frames, so pyct is below it
    monkeypatch.setattr(values, "caller_site", broken)

    code = main(["run", TARGET, '{"x": 3}'])

    assert code == 1
    captured = capsys.readouterr()
    line = one_line(captured.out)
    assert line["failure"] == {"kind": "pyct_bug", "detail": "RuntimeError: boom"}
    # the traceback a person needs to fix pyct sits under the ended line, indented
    trace = captured.err.splitlines()
    ended = trace.index("ended pyct bug: RuntimeError: boom")
    assert trace[ended + 1] == "    Traceback (most recent call last):"


# trace-the-seed-records-a-downgrade
def test_records_a_downgrade() -> None:
    result = run_pyct(THROUGH_ABS, '{"x": -3}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    # abs drops the condition, so the name of the call it went through is all that is left
    assert line["downgrades"] == ["__abs__"]
    # y is a plain int after abs, so `y < 10` is Python's own compare and no fork is recorded
    assert line["forks"] == []
    assert line["covered"] == {THROUGH_ABS_FILE: [2, 3, 4]}
    # the def and the four body lines
    assert line["total"] == {THROUGH_ABS_FILE: 5}


# trace-the-seed-writes-readable-trace-to-stderr
def test_writes_a_readable_trace_to_stderr() -> None:
    result = run_pyct(CALLS_HELPER, '{"x": 50}')

    assert result.returncode == 0, result.stderr
    # one fact per line: the seed, each fork in order, the coverage, how it ended, what was lost
    assert result.stderr.splitlines() == [
        'seed {"x": 50}',
        f"fork {HELPER_CHECK_FILE}:2:7  x < 5  not taken",
        f"fork {CALLS_HELPER_FILE}:7:7  x < 100  taken",
        f"covered 3 of 7 lines in {CALLS_HELPER_FILE}",
        "ended returned",
        "downgrades none",
    ]
    assert len(result.stdout.splitlines()) == 1, result.stdout

    lost = run_pyct(THROUGH_ABS, '{"x": -3}')

    assert "downgrades __abs__" in lost.stderr.splitlines()

    raised = run_pyct(RAISES, '{"x": 3}')

    assert "ended target raised: ValueError: too small" in raised.stderr.splitlines()
