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
    """Bad module path should be rejected with a message naming the module.

    This test requires the CLI to actually parse argv and attempt the
    import — a generic "pyct has no __main__" failure is NOT a pass.
    """
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

    output = (result.stderr + result.stdout).lower()
    assert result.returncode != 0
    # The bad module name must appear in the output — proves the CLI
    # processed argv and reached the import attempt, not just bailed
    # out at module loading.
    assert "does.not.exist" in output


def test_cli_with_malformed_json_args_fails_with_nonzero_exit():
    """Malformed --args JSON should be rejected with a JSON-specific error.

    This test requires the CLI to actually parse the --args flag — a
    generic "pyct has no __main__" failure is NOT a pass.
    """
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

    output = (result.stderr + result.stdout).lower()
    assert result.returncode != 0
    # One of these markers must appear — they prove the CLI reached the
    # JSON parsing step rather than failing at module discovery.
    assert "json" in output or "--args" in output or "invalid args" in output
