"""Acceptance tests for compare-coverage-on-the-fixtures: refusals before any target runs.

Each leaves stdout empty. A usage error exits 2, a bad legacy checkout exits 2 and a missing
cvc5 exits 1, as ``pyct run`` does.
"""

import json
from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import ONE_CHECK, REPO_ROOT, run_checker
from tests.compare_coverage.conftest import StubCheckout


@pytest.mark.parametrize(
    ("legacy", "says"),
    [
        (None, "--legacy is required"),
        ("empty", "no environment at"),
        ("v2", "not a checkout of main"),
    ],
)
def test_refuses_a_bad_legacy_checkout(tmp_path: Path, legacy: str | None, says: str) -> None:
    """compare-coverage-against-legacy-refuses-a-bad-legacy-checkout"""
    given = {"empty": ["--legacy", str(tmp_path)], "v2": ["--legacy", str(REPO_ROOT)]}

    result = run_checker(*given.get(legacy or "", []), "--target", ONE_CHECK)

    assert says in result.stderr
    assert "git worktree add DIR main && uv sync --project DIR --frozen" in result.stderr
    assert result.stdout == ""
    assert result.returncode == 2


@pytest.mark.parametrize(
    ("flags", "says"),
    [
        (["--set", "nope"], "--set: no set named 'nope'"),
        (["--target", "targets.nope::f"], "--target: no entry runs 'targets.nope::f'"),
        (["--budget", "0"], "--budget must be a finite number of seconds above zero, got '0'"),
        (["--plateau", "2.5"], "--plateau must be a whole number above zero, got '2.5'"),
        (["--solver-timeout", "inf"], "--solver-timeout must be a finite number of seconds"),
        (["--accept"], "--accept needs --accepted FILE"),
        (["--bogus"], "unrecognized arguments: --bogus"),
        (["--accepted", "missing.jsonl"], "--accepted: cannot read missing.jsonl"),
        (["--accepted", "not-a-record.jsonl"], "--accepted: not-a-record.jsonl line 2"),
    ],
)
def test_refuses_a_bad_flag(
    stub_checkout: StubCheckout, tmp_path: Path, flags: list[str], says: str
) -> None:
    """compare-coverage-against-legacy-refuses-a-bad-flag"""
    record = json.dumps(
        {"set": "v2", "target": "m::f", "seed": {}, "status": "differs"}
        | {"only_legacy": [], "only_v2": []}
    )
    (tmp_path / "not-a-record.jsonl").write_text(f"{record}\n[1, 2]\n")
    flags = [str(tmp_path / flag) if flag.endswith(".jsonl") else flag for flag in flags]
    says = says.replace("missing.jsonl", str(tmp_path / "missing.jsonl"))
    says = says.replace("not-a-record.jsonl", str(tmp_path / "not-a-record.jsonl"))

    result = run_checker("--legacy", str(stub_checkout.path), *flags)

    assert says in result.stderr
    assert result.stdout == ""
    assert result.returncode == 2
    assert not (stub_checkout.path / "calls.jsonl").exists()


def test_stops_without_cvc5(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-stops-without-cvc5"""
    empty = tmp_path / "bin"
    empty.mkdir()

    result = run_checker(
        "--legacy", str(stub_checkout.path), "--target", ONE_CHECK, path=str(empty)
    )

    assert f"cvc5 was not found on PATH (looked in: {empty})" in result.stderr
    assert "install it from https://cvc5.github.io/ (brew install cvc5)" in result.stderr
    assert result.stdout == ""
    assert result.returncode == 1
    assert not (stub_checkout.path / "calls.jsonl").exists()
