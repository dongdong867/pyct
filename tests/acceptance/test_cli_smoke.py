"""Acceptance tests for CLI subprocess invocation (behavior 17)."""

import subprocess
import sys


def test_cli_runs_target_function_end_to_end():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyct",
            "run",
            "tests.acceptance.fixtures.branches.single_if_else::classify",
            "--args",
            '{"x": 0}',
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert "coverage" in result.stdout.lower() or "success" in result.stdout.lower()


def test_cli_with_nonexistent_module_fails_with_nonzero_exit():
    """Bad module path should fail cleanly, not crash the CLI."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyct",
            "run",
            "does.not.exist::whatever",
            "--args",
            '{"x": 0}',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    # Error message should mention the problem, in stderr or stdout
    assert (
        "does.not.exist" in (result.stderr + result.stdout).lower()
        or "error" in (result.stderr + result.stdout).lower()
    )


def test_cli_with_malformed_json_args_fails_with_nonzero_exit():
    """Malformed --args JSON should be rejected with a clear error."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyct",
            "run",
            "tests.acceptance.fixtures.branches.single_if_else::classify",
            "--args",
            "{not valid json}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
