"""Unit tests for pyct.contracts primitives + discovery.

Task 1 scope: Contract / ContractSet / EMPTY_CONTRACTS dataclasses,
discover_contracts (getattr-default path), and _check_preconditions
(empty / violation / soft-fail-on-missing-param / soft-fail-on-raise).
The pre / post decorators are introduced in Task 2.
"""

from __future__ import annotations

import logging


def test_module_exports():
    from pyct.contracts import (
        EMPTY_CONTRACTS,
        Contract,
        ContractSet,
        discover_contracts,
    )

    assert isinstance(EMPTY_CONTRACTS, ContractSet)
    assert EMPTY_CONTRACTS.requires == ()
    assert EMPTY_CONTRACTS.ensures == ()
    assert callable(discover_contracts)
    assert Contract is not None


def test_discover_contracts_returns_empty_for_undecorated():
    from pyct.contracts import EMPTY_CONTRACTS, discover_contracts

    def f(x):
        return x

    assert discover_contracts(f) is EMPTY_CONTRACTS


def test_check_preconditions_returns_none_on_empty_set():
    from pyct.contracts import EMPTY_CONTRACTS
    from pyct.engine.engine import _check_preconditions

    assert _check_preconditions(EMPTY_CONTRACTS, {"x": 1}) is None


def _make_require(
    *,
    predicate,
    description: str = "",
    source: str = "<test>:0",
    condition_args: tuple[str, ...] = (),
):
    from pyct.contracts import Contract, ContractSet

    contract = Contract(
        predicate=predicate,
        description=description,
        source=source,
        condition_args=condition_args,
    )
    return ContractSet(requires=(contract,))


def test_check_preconditions_returns_violation_string_on_failing_require():
    from pyct.engine.engine import _check_preconditions

    contracts = _make_require(
        predicate=lambda x: x > 0,
        description="x > 0",
        source="examples/foo.py:12",
        condition_args=("x",),
    )

    out = _check_preconditions(contracts, {"x": -1})

    assert out is not None
    assert out.startswith("precondition_violated: ")
    assert "examples/foo.py:12" in out


def test_check_preconditions_soft_fail_on_missing_param(caplog):
    from pyct.engine.engine import _check_preconditions

    contracts = _make_require(
        predicate=lambda missing: missing > 0,
        description="missing > 0",
        source="<t>:1",
        condition_args=("missing",),
    )

    with caplog.at_level(logging.WARNING, logger="ct.engine"):
        result = _check_preconditions(contracts, {"x": 1})

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARN about the missing parameter"
    assert any("missing" in r.getMessage() for r in warnings)


def test_check_preconditions_soft_fail_on_predicate_exception(caplog):
    from pyct.engine.engine import _check_preconditions

    def boom(x):
        raise RuntimeError("nope")

    contracts = _make_require(
        predicate=boom,
        description="x > 0",
        source="<t>:2",
        condition_args=("x",),
    )

    with caplog.at_level(logging.WARNING, logger="ct.engine"):
        result = _check_preconditions(contracts, {"x": 1})

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARN about the raising predicate"
    msg = " ".join(r.getMessage() for r in warnings)
    assert "<t>:2" in msg
    assert "RuntimeError" in msg
