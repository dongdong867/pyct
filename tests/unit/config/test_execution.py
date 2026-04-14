"""Unit tests for ExecutionConfig."""

import pytest

from pyct.config.execution import ExecutionConfig


class TestExecutionConfigDefaults:
    def test_default_timeout_is_thirty_seconds(self):
        config = ExecutionConfig()
        assert config.timeout_seconds == 30.0

    def test_default_max_iterations_is_fifty(self):
        config = ExecutionConfig()
        assert config.max_iterations == 50

    def test_default_solver_is_cvc5(self):
        config = ExecutionConfig()
        assert config.solver == "cvc5"

    def test_default_solver_timeout_is_ten(self):
        config = ExecutionConfig()
        assert config.solver_timeout == 10

    def test_default_plateau_threshold_is_five(self):
        config = ExecutionConfig()
        assert config.plateau_threshold == 5


class TestExecutionConfigCustomValues:
    def test_custom_timeout_accepted(self):
        config = ExecutionConfig(timeout_seconds=60.0)
        assert config.timeout_seconds == 60.0

    def test_custom_max_iterations_accepted(self):
        config = ExecutionConfig(max_iterations=100)
        assert config.max_iterations == 100

    def test_all_custom_values(self):
        config = ExecutionConfig(
            timeout_seconds=120.0,
            max_iterations=200,
            solver="z3",
            solver_timeout=30,
            plateau_threshold=10,
        )
        assert config.timeout_seconds == 120.0
        assert config.max_iterations == 200
        assert config.solver == "z3"
        assert config.solver_timeout == 30
        assert config.plateau_threshold == 10


class TestExecutionConfigImmutability:
    def test_cannot_mutate_timeout_after_construction(self):
        config = ExecutionConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.timeout_seconds = 60.0  # type: ignore

    def test_cannot_mutate_max_iterations(self):
        config = ExecutionConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.max_iterations = 100  # type: ignore


class TestExecutionConfigBoundaryValues:
    """Characterization tests for boundary-value behavior.

    These document the current *permissive* contract: ExecutionConfig
    accepts degenerate values (zero, negative, empty) without raising.
    The engine is expected to handle sanity checks at use time, not at
    config construction.
    """

    def test_zero_max_iterations_accepted(self):
        config = ExecutionConfig(max_iterations=0)
        assert config.max_iterations == 0

    def test_negative_timeout_seconds_accepted(self):
        config = ExecutionConfig(timeout_seconds=-1.0)
        assert config.timeout_seconds == -1.0

    def test_zero_plateau_threshold_accepted(self):
        config = ExecutionConfig(plateau_threshold=0)
        assert config.plateau_threshold == 0

    def test_empty_solver_name_accepted(self):
        config = ExecutionConfig(solver="")
        assert config.solver == ""


class TestExecutionConfigErrorCases:
    def test_unknown_field_raises_type_error(self):
        with pytest.raises(TypeError):
            ExecutionConfig(not_a_field=42)  # type: ignore

    def test_delete_field_raises_on_frozen_config(self):
        config = ExecutionConfig()
        with pytest.raises((AttributeError, TypeError)):
            del config.timeout_seconds  # type: ignore
