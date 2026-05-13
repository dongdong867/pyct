"""Unit tests for engine precondition short-circuit telemetry and helper."""

from __future__ import annotations

import logging

import pytest

from pyct.engine.engine import _build_result
from pyct.engine.result import ExplorationResult, RunConcolicResult
from pyct.engine.state import ExplorationState


def test_state_preconditions_violated_defaults_to_zero() -> None:
    state = ExplorationState()
    assert state.preconditions_violated == 0


def test_exploration_result_default_preconditions_violated_zero() -> None:
    fields_default = ExplorationResult.__dataclass_fields__["preconditions_violated"].default
    assert fields_default == 0


def test_build_result_threads_preconditions_violated_from_state() -> None:
    state = ExplorationState()
    state.preconditions_violated = 3
    state.termination_reason = "exhausted"
    result = _build_result(state, last_error=None)
    assert result.preconditions_violated == 3


def test_run_concolic_result_default_preconditions_violated_zero() -> None:
    fields_default = RunConcolicResult.__dataclass_fields__["preconditions_violated"].default
    assert fields_default == 0


def test_from_exploration_threads_preconditions_violated() -> None:
    exploration = ExplorationResult(
        success=True,
        coverage_percent=0.0,
        executed_lines=frozenset(),
        paths_explored=0,
        iterations=0,
        termination_reason="exhausted",
        elapsed_seconds=0.0,
        preconditions_violated=7,
    )
    public = RunConcolicResult.from_exploration(exploration, inputs=[])
    assert public.preconditions_violated == 7


def test_check_preconditions_returns_none_on_empty_contract_set() -> None:
    from pyct.contracts import EMPTY_CONTRACTS
    from pyct.engine.engine import _check_preconditions

    assert _check_preconditions(EMPTY_CONTRACTS, {"x": 1}) is None


def test_check_preconditions_returns_error_with_source_and_description() -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    contract = Contract(
        predicate=lambda x: x > 0,
        description="x must be positive",
        source="example.py:42",
        condition_args=("x",),
    )
    contracts = ContractSet(requires=(contract,))

    error = _check_preconditions(contracts, {"x": -1})

    assert error is not None
    assert error.startswith("precondition_violated:")
    assert "example.py:42" in error
    assert "x must be positive" in error


def test_check_preconditions_returns_none_when_predicate_passes() -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    contract = Contract(
        predicate=lambda x: x > 0,
        description="x positive",
        source="example.py:1",
        condition_args=("x",),
    )
    contracts = ContractSet(requires=(contract,))

    assert _check_preconditions(contracts, {"x": 5}) is None


def test_check_preconditions_omits_trailing_space_when_description_none() -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    contract = Contract(
        predicate=lambda x: x > 0,
        description=None,
        source="example.py:7",
        condition_args=("x",),
    )
    contracts = ContractSet(requires=(contract,))

    error = _check_preconditions(contracts, {"x": -1})

    assert error == "precondition_violated: example.py:7"


def test_check_preconditions_binds_only_condition_args_subset() -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    captured: dict[str, object] = {}

    def spy_predicate(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    contract = Contract(
        predicate=spy_predicate,
        description=None,
        source="example.py:1",
        condition_args=("x",),
    )
    contracts = ContractSet(requires=(contract,))

    _check_preconditions(contracts, {"x": 9, "y": 100, "z": "ignored"})

    assert captured == {"x": 9}


def test_check_preconditions_logs_warning_and_proceeds_on_predicate_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    def boom(x: int) -> bool:
        raise ValueError("predicate broke")

    contract = Contract(
        predicate=boom,
        description="x must be positive",
        source="example.py:10",
        condition_args=("x",),
    )
    contracts = ContractSet(requires=(contract,))

    with caplog.at_level(logging.WARNING, logger="ct.engine"):
        result = _check_preconditions(contracts, {"x": 5})

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "example.py:10" in message
    assert "x must be positive" in message
    assert "ValueError" in message


def test_check_preconditions_short_circuits_at_first_false_require() -> None:
    from pyct.contracts import Contract, ContractSet
    from pyct.engine.engine import _check_preconditions

    later_called = False

    def first_failing(x: int) -> bool:
        return False

    def later_predicate(x: int) -> bool:
        nonlocal later_called
        later_called = True
        return True

    contracts = ContractSet(
        requires=(
            Contract(
                predicate=first_failing,
                description="first fail",
                source="example.py:1",
                condition_args=("x",),
            ),
            Contract(
                predicate=later_predicate,
                description="never reached",
                source="example.py:2",
                condition_args=("x",),
            ),
        )
    )

    error = _check_preconditions(contracts, {"x": 0})

    assert error is not None
    assert "example.py:1" in error
    assert "first fail" in error
    assert later_called is False
