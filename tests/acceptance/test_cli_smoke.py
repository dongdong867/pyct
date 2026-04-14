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
