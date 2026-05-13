"""Acceptance tests for icontract contract discovery during exploration."""

from __future__ import annotations

import logging

import pytest


def test_run_concolic_logs_discovered_contracts(caplog: pytest.LogCaptureFixture) -> None:
    """
    Given a target decorated with icontract preconditions and postconditions
    When run_concolic explores the target in-process
    Then the ct.contracts logger should emit an INFO line reporting the counts
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.contracts.basic import positive_double

    with caplog.at_level(logging.INFO, logger="ct.contracts"):
        result = run_concolic(
            target=positive_double,
            initial_args={"x": 1},
            isolated=False,
        )

    assert result.success
    discovery_logs = [
        r for r in caplog.records if r.levelno == logging.INFO and "discovered" in r.message.lower()
    ]
    assert len(discovery_logs) >= 1
    assert any("precondition" in r.message for r in discovery_logs)
    assert any("postcondition" in r.message for r in discovery_logs)


def test_run_concolic_does_not_log_when_target_has_no_contracts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given a target with no icontract decorators
    When run_concolic explores it in-process
    Then no contract-discovery INFO message should be emitted
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.contracts.basic import no_contracts

    with caplog.at_level(logging.INFO, logger="ct.contracts"):
        run_concolic(target=no_contracts, initial_args={"x": 1}, isolated=False)

    discovery_logs = [
        r for r in caplog.records if r.levelno == logging.INFO and "discovered" in r.message.lower()
    ]
    assert discovery_logs == []
