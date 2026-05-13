"""Unit tests for engine precondition short-circuit telemetry and helper."""

from __future__ import annotations

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
