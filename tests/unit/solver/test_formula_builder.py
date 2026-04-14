"""Tests for FormulaBuilder."""

from __future__ import annotations

from unittest.mock import MagicMock

from pyct.predicate import Predicate
from pyct.solver.formula_builder import FormulaBuilder


def _mock_constraint(predicates):
    """Create a mock constraint that returns the given predicates."""
    mock = MagicMock()
    mock.get_path_predicates.return_value = predicates
    return mock


class TestBuildConstraintFormula:
    """build_constraint_formula produces complete SMT-LIB2 output."""

    def test_includes_header_and_check_sat(self):
        builder = FormulaBuilder()
        constraint = _mock_constraint([])
        formula = builder.build_constraint_formula(constraint, {})
        assert "(set-logic ALL)" in formula
        assert "(check-sat)" in formula

    def test_declarations(self):
        builder = FormulaBuilder()
        constraint = _mock_constraint([])
        var_types = {"x_VAR": "Int", "y_VAR": "Bool"}
        formula = builder.build_constraint_formula(constraint, var_types)
        assert "(declare-const x_VAR Int)" in formula
        assert "(declare-const y_VAR Bool)" in formula

    def test_assertions_from_predicates(self):
        builder = FormulaBuilder()
        predicates = [
            Predicate(["<", "x_VAR", "10"], True),
            Predicate([">", "y_VAR", "0"], True),
        ]
        constraint = _mock_constraint(predicates)
        formula = builder.build_constraint_formula(constraint, {"x_VAR": "Int", "y_VAR": "Int"})
        assert "(assert (< x_VAR 10))" in formula
        assert "(assert (> y_VAR 0))" in formula

    def test_get_value_commands(self):
        builder = FormulaBuilder()
        constraint = _mock_constraint([])
        formula = builder.build_constraint_formula(constraint, {"x_VAR": "Int"})
        assert "(get-value (x_VAR))" in formula


class TestBuildValidationFormula:
    """build_validation_formula for int/float/string validation."""

    def test_int_exact_equality(self):
        builder = FormulaBuilder()
        formula = builder.build_validation_formula("x_VAR", 42, is_float=False)
        assert "(assert (= x_VAR 42))" in formula
        assert "(check-sat)" in formula

    def test_float_epsilon_comparison(self):
        builder = FormulaBuilder()
        formula = builder.build_validation_formula("x_VAR", 3.14, is_float=True)
        assert "epsilon" not in formula  # epsilon is inlined
        assert "<=" in formula
        assert "(check-sat)" in formula

    def test_string_equality(self):
        builder = FormulaBuilder()
        formula = builder.build_validation_formula("s_VAR", "hello", is_float=False)
        assert '(assert (= s_VAR "hello"))' in formula
