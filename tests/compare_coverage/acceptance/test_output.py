"""Acceptance tests for compare-coverage-on-the-fixtures: what stdout and stderr carry.

Legacy is the stub engine here, so its answers are exact; v2 is the real ``pyct run``.
"""

import json
import platform
import subprocess
import sys

from tests.compare_coverage.acceptance.checker import (
    IMPLIED_CHECK,
    ONE_CHECK,
    REPO_ROOT,
    one_row,
    rows,
    run_checker,
    summary,
    table_rows,
)
from tests.compare_coverage.conftest import StubCheckout


def test_flags_a_difference(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-flags-a-difference"""
    stub_checkout.script({IMPLIED_CHECK: {"lines": [2, 3, 4, 5, 6]}})

    result = run_checker("--legacy", str(stub_checkout.path), "--target", IMPLIED_CHECK)

    row = one_row(result.stdout, result.stderr)
    assert row["status"] == "differs"
    assert row["only_legacy"] == [5]
    assert row["only_v2"] == []
    (line,) = table_rows(result.stderr, IMPLIED_CHECK)
    assert "differs" in line
    assert "only legacy: 5" in line
    assert result.returncode == 1


def test_runs_both_sides_under_the_same_limits(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-runs-both-sides-under-the-same-limits"""
    default = run_checker("--legacy", str(stub_checkout.path), "--target", ONE_CHECK)

    same = {"budget": 30.0, "plateau": 5, "solver_timeout": 10}
    assert summary(default.stdout, default.stderr)["limits"] == {"v2": same, "legacy": same}

    flags = ("--budget", "5", "--plateau", "3", "--solver-timeout", "2.5")
    given = run_checker("--legacy", str(stub_checkout.path), "--target", ONE_CHECK, *flags)

    assert summary(given.stdout, given.stderr)["limits"] == {
        "v2": {"budget": 5.0, "plateau": 3, "solver_timeout": 2.5},
        "legacy": {"budget": 5.0, "plateau": 3, "solver_timeout": 3},
    }
    # what legacy's engine was handed, as the stub recorded it
    config = stub_checkout.calls()[-1]["config"]
    assert config["timeout_seconds"] == config["seed_soft_timeout"] == 5.0
    assert config["plateau_threshold"] == 3
    assert config["solver_timeout"] == 3
    assert config["max_iterations"] == sys.maxsize


def test_keeps_data_on_stdout(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-keeps-data-on-stdout"""
    stub_checkout.script(
        {IMPLIED_CHECK: {"lines": [2, 3, 4, 5, 6]}, ONE_CHECK: {"lines": [2, 3, 4]}}
    )

    result = run_checker(
        "--legacy", str(stub_checkout.path), "--target", ONE_CHECK, "--target", IMPLIED_CHECK
    )

    # every stdout line is JSON: the rows in list order, then the summary line
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    targets = [line["target"] for line in rows(result.stdout, result.stderr)]
    assert targets == [IMPLIED_CHECK, ONE_CHECK]
    closing = summary(result.stdout, result.stderr)
    assert "target" not in closing
    assert closing["statuses"]["same"] == 1
    assert closing["statuses"]["differs"] == 1
    assert len(lines) == 3
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    # the stub checkout is no git checkout, so it has no commit to name
    assert closing["commits"] == {"v2": head.stdout.strip(), "legacy": None}
    here = platform.python_version()
    assert closing["environment"]["python"] == {"v2": here, "legacy": here}
    assert closing["environment"]["platform"] == platform.platform()
    assert closing["environment"]["cvc5"].startswith("cvc5")
    # the table is on stderr, and a table line is no JSON
    (line,) = table_rows(result.stderr, ONE_CHECK)
    assert "covered 3 of 3" in line
