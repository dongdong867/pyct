from __future__ import annotations

from typing import Any


class FormulaBuilder:
    """Builds SMT-LIB2 formulas for solver input."""

    LOGIC = "ALL"
    VAR_SUFFIX = "_VAR"

    def build_constraint_formula(self, constraint: Any, var_to_types: dict[str, str]) -> str:
        """
        Build complete SMT formula from constraint.

        Args:
            constraint: Constraint object with assertions
            var_to_types: Mapping of variable names to SMT types

        Returns:
            Complete SMT-LIB2 formula string
        """
        parts = [
            self._build_header(),
            self._build_declarations(var_to_types),
            self._build_assertions(constraint),
            self._build_check_sat(),
            self._build_get_values(var_to_types),
        ]

        return "\n".join(parts) + "\n"

    def build_validation_formula(self, expr: str, value: Any, is_float: bool) -> str:
        """
        Build formula to validate that expression equals value.

        Args:
            expr: Expression formula
            value: Expected value
            is_float: Whether value is a float (use approximate comparison)

        Returns:
            SMT-LIB2 formula for validation
        """
        from pyct.utils.smt_converter import py2smt

        value_smt = py2smt(value)

        if is_float:
            # For floats, check if difference is within tolerance
            epsilon = "(/ 1 1000000000000000)"
            formula = (
                f"(assert (and "
                f"(<= (- {epsilon}) (- {expr} {value_smt})) "
                f"(<= (- {expr} {value_smt}) {epsilon})"
                f"))\n(check-sat)"
            )
        else:
            # For other types, exact equality
            formula = f"(assert (= {expr} {value_smt}))\n(check-sat)"

        return formula

    def _build_header(self) -> str:
        """Build SMT header with logic and options."""
        return f"(set-logic {self.LOGIC})\n(set-option :strings-exp true)"

    def _build_declarations(self, var_to_types: dict[str, str]) -> str:
        """Build variable declarations."""
        declarations = [
            f"(declare-const {name} {var_type})" for name, var_type in var_to_types.items()
        ]
        return "\n".join(declarations)

    def _build_assertions(self, constraint: Any) -> str:
        """Build assertions from constraint."""
        assertions = [assertion.get_formula() for assertion in constraint.get_path_predicates()]
        return "\n".join(assertions)

    def _build_check_sat(self) -> str:
        """Build check-sat command."""
        return "(check-sat)"

    def _build_get_values(self, var_to_types: dict[str, str]) -> str:
        """Build get-value commands."""
        get_values = [f"(get-value ({name}))" for name in var_to_types]
        return "\n".join(get_values)
