"""Unit tests for input telemetry data model.

Covers the leaf module ``pyct.engine.types`` introduced for the per-input
telemetry feature: the ``Provenance`` and ``Outcome`` string enums and the
``InputRecord`` frozen dataclass.

The pickle round-trip tests are load-bearing for the subprocess boundary
between the engine and ``isolated_runner`` — the records must survive
serialization with their enum identity and frozenset typing intact.
"""

import pickle

import pytest

from pyct.engine.types import InputRecord, Outcome, Provenance


class TestProvenance:
    def test_seed_value_is_lowercase_snake_case(self):
        assert Provenance.SEED.value == "seed"

    def test_solver_value_is_lowercase_snake_case(self):
        assert Provenance.SOLVER.value == "solver"

    def test_plugin_seed_value_is_lowercase_snake_case(self):
        assert Provenance.PLUGIN_SEED.value == "plugin_seed"

    def test_plugin_plateau_value_is_lowercase_snake_case(self):
        assert Provenance.PLUGIN_PLATEAU.value == "plugin_plateau"

    def test_plugin_unknown_value_is_lowercase_snake_case(self):
        assert Provenance.PLUGIN_UNKNOWN.value == "plugin_unknown"

    def test_pickle_round_trip_preserves_enum_identity(self):
        restored = pickle.loads(pickle.dumps(Provenance.PLUGIN_PLATEAU))
        assert restored is Provenance.PLUGIN_PLATEAU

    def test_str_enum_compares_equal_to_its_value(self):
        assert Provenance.SEED == "seed"


class TestOutcome:
    def test_covered_new_value_is_lowercase_snake_case(self):
        assert Outcome.COVERED_NEW.value == "covered_new"

    def test_no_gain_value_is_lowercase_snake_case(self):
        assert Outcome.NO_GAIN.value == "no_gain"

    def test_target_error_value_is_lowercase_snake_case(self):
        assert Outcome.TARGET_ERROR.value == "target_error"

    def test_timeout_value_is_lowercase_snake_case(self):
        assert Outcome.TIMEOUT.value == "timeout"

    def test_pickle_round_trip_preserves_enum_identity(self):
        restored = pickle.loads(pickle.dumps(Outcome.TARGET_ERROR))
        assert restored is Outcome.TARGET_ERROR

    def test_str_enum_compares_equal_to_its_value(self):
        assert Outcome.NO_GAIN == "no_gain"


class TestInputRecord:
    def test_constructible_with_all_fields(self):
        record = InputRecord(
            args={"x": 1},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({1, 2}),
            error=None,
        )
        assert record.args == {"x": 1}
        assert record.provenance is Provenance.SEED
        assert record.outcome is Outcome.COVERED_NEW
        assert record.new_lines == frozenset({1, 2})
        assert record.error is None

    def test_carries_error_message_when_outcome_is_target_error(self):
        record = InputRecord(
            args={"x": -1},
            provenance=Provenance.SOLVER,
            outcome=Outcome.TARGET_ERROR,
            new_lines=frozenset(),
            error="ValueError: bad input",
        )
        assert record.error == "ValueError: bad input"

    def test_record_is_frozen(self):
        record = InputRecord(
            args={"x": 1},
            provenance=Provenance.SEED,
            outcome=Outcome.NO_GAIN,
            new_lines=frozenset(),
            error=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            record.error = "oops"  # type: ignore

    def test_records_with_same_fields_compare_equal(self):
        first = InputRecord(
            args={"x": 1},
            provenance=Provenance.SOLVER,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({3}),
            error=None,
        )
        second = InputRecord(
            args={"x": 1},
            provenance=Provenance.SOLVER,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({3}),
            error=None,
        )
        assert first == second

    def test_records_with_different_provenance_compare_unequal(self):
        first = InputRecord(
            args={"x": 1},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({3}),
            error=None,
        )
        second = InputRecord(
            args={"x": 1},
            provenance=Provenance.PLUGIN_SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({3}),
            error=None,
        )
        assert first != second

    def test_pickle_round_trip_preserves_all_fields(self):
        original = InputRecord(
            args={"name": "alice", "age": 30},
            provenance=Provenance.PLUGIN_UNKNOWN,
            outcome=Outcome.TARGET_ERROR,
            new_lines=frozenset({10, 20, 30}),
            error="ValueError: bad input",
        )
        restored = pickle.loads(pickle.dumps(original))
        assert restored == original
        assert restored.provenance is Provenance.PLUGIN_UNKNOWN
        assert restored.outcome is Outcome.TARGET_ERROR
        assert isinstance(restored.new_lines, frozenset)
        assert restored.error == "ValueError: bad input"

    def test_pickle_round_trip_preserves_empty_record_fields(self):
        original = InputRecord(
            args={},
            provenance=Provenance.SEED,
            outcome=Outcome.NO_GAIN,
            new_lines=frozenset(),
            error=None,
        )
        restored = pickle.loads(pickle.dumps(original))
        assert restored == original
        assert isinstance(restored.new_lines, frozenset)
