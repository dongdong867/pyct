"""Acceptance tests for CLI subprocess invocation (behavior 17)."""

import subprocess
import sys


def test_cli_runs_target_function_end_to_end():
    """
    Given the pyct CLI and a valid `module::function` target
    When invoked via `python -m pyct run` with a JSON args blob
    Then the subprocess should exit 0
      And stdout should mention coverage or success
    """
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
    """
    Given a bogus `module.path::function` argument to the CLI
    When the subprocess attempts to import the module
    Then the exit code should be non-zero
      And the error output should name the bad module path
          (proves the CLI reached import, not just module-loader failure)
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
    assert "does.not.exist" in output


def test_cli_with_malformed_json_args_fails_with_nonzero_exit():
    """
    Given a syntactically invalid --args JSON payload
    When the CLI parses the flag
    Then the exit code should be non-zero
      And output should mention JSON, --args, or "invalid args"
          (proves the CLI reached argument validation, not module loading)
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
    assert "json" in output or "--args" in output or "invalid args" in output
