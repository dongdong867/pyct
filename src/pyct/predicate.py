from __future__ import annotations

from enum import Enum
from typing import Any

from pyct.core import Concolic


class FormulaDepth(Enum):
    """Depth mode for formula generation."""

    DEEP = "deep"  # Recursively expand all concolic expressions
    SHALLOW = "shallow"  # Use concrete values for concolic objects


SymbolicExpression = str | list[Any] | Concolic | bool | int | float


class Predicate:
    """
    Represents a boolean predicate in symbolic execution.

    A predicate consists of:
    - expr: Symbolic expression (may contain Concolic objects)
    - value: Boolean value (True or False)

    The predicate represents the assertion: expr == value

    Attributes:
        expr: Symbolic expression
        value: Boolean value for the expression

    Examples:
        >>> pred = Predicate(["<", "x", "10"], True)
        >>> pred.get_formula()
        "(assert (< x 10))"

        >>> pred2 = Predicate([">=", "x", "10"], False)
        >>> pred2.get_formula()
        "(assert (not (>= x 10)))"
    """

    def __init__(self, expr: SymbolicExpression, value: bool) -> None:
        """
        Initialize a predicate.

        Args:
            expr: Symbolic expression (string, list, or Concolic)
            value: Boolean value (True or False)
        """
        self.expr = expr
        self.value = value

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another predicate.

        Two predicates are equal if they have the same value and
        equivalent expressions (considering concolic objects).

        Args:
            other: Object to compare with

        Returns:
            True if predicates are equal

        Examples:
            >>> p1 = Predicate(["<", "x", "10"], True)
            >>> p2 = Predicate(["<", "x", "10"], True)
            >>> p1 == p2
            True
        """
        if not isinstance(other, Predicate):
            return NotImplemented

        return self.value == other.value and self._expressions_equal(self.expr, other.expr)

    def __str__(self) -> str:
        """
        String representation of the predicate.

        Returns:
            Human-readable string showing expression and value
        """
        expr_str = self.get_formula_deep(self.expr)
        return f"{expr_str} = {self.value}"

    def __repr__(self) -> str:
        """
        Developer-friendly representation.

        Returns:
            String showing Predicate with expr and value
        """
        return f"Predicate(expr={self.expr!r}, value={self.value})"

    # ========================================================================
    # Equality Checking
    # ========================================================================

    def _expressions_equal(self, expr1: SymbolicExpression, expr2: SymbolicExpression) -> bool:
        """
        Check if two expressions are equivalent.

        This method recursively compares expressions, unwrapping concolic
        objects to compare their underlying symbolic representations.

        Args:
            expr1: First expression
            expr2: Second expression

        Returns:
            True if expressions are equivalent

        Examples:
            >>> cb1 = ConcolicBool(True, "x", engine)
            >>> cb2 = ConcolicBool(True, "x", engine)
            >>> pred._expressions_equal(cb1, cb2)
            True
        """
        # Both are concolic objects - compare their expressions
        if isinstance(expr1, Concolic) and isinstance(expr2, Concolic):
            return self._expressions_equal(expr1.expr, expr2.expr)

        # Both are lists - compare element-wise
        if isinstance(expr1, list) and isinstance(expr2, list):
            return self._lists_equal(expr1, expr2)

        # Primitive comparison
        return expr1 == expr2

    def _lists_equal(self, list1: list[Any], list2: list[Any]) -> bool:
        """
        Check if two expression lists are equal.

        Args:
            list1: First list
            list2: Second list

        Returns:
            True if lists have same length and all elements are equal
        """
        if len(list1) != len(list2):
            return False

        return all(self._expressions_equal(e1, e2) for e1, e2 in zip(list1, list2, strict=False))

    # ========================================================================
    # Formula Generation
    # ========================================================================

    def get_formula(self) -> str:
        """
        Generate SMT-LIB2 assertion formula for this predicate.

        Returns:
            SMT assertion string

        Examples:
            >>> pred = Predicate(["<", "x", "10"], True)
            >>> pred.get_formula()
            "(assert (< x 10))"

            >>> pred = Predicate([">=", "x", "10"], False)
            >>> pred.get_formula()
            "(assert (not (>= x 10)))"
        """
        formula = self.get_formula_deep(self.expr)

        # Negate if value is False
        if not self.value:
            formula = f"(not {formula})"

        return f"(assert {formula})"

    @staticmethod
    def get_formula_deep(expr: SymbolicExpression) -> str:
        """
        Generate formula with deep expansion of concolic objects.

        Recursively expands all concolic objects to their symbolic expressions.

        Args:
            expr: Expression to convert

        Returns:
            SMT-LIB2 formula string

        Examples:
            >>> Predicate.get_formula_deep(["<", "x", "10"])
            "(< x 10)"

            >>> cb = ConcolicBool(True, ["=", "y", "5"], engine)
            >>> Predicate.get_formula_deep(["and", cb, "z"])
            "(and (= y 5) z)"
        """
        return Predicate._generate_formula(expr, FormulaDepth.DEEP)

    @staticmethod
    def get_formula_shallow(expr: SymbolicExpression) -> str:
        """
        Generate formula with shallow expansion (use concrete values).

        Uses concrete values for concolic objects instead of their expressions.

        Args:
            expr: Expression to convert

        Returns:
            SMT-LIB2 formula string

        Examples:
            >>> Predicate.get_formula_shallow("x")
            "x"

            >>> cb = ConcolicBool(True, ["=", "y", "5"], engine)
            >>> Predicate.get_formula_shallow(["and", cb, "z"])
            "(and true z)"
        """
        return Predicate._generate_formula(expr, FormulaDepth.SHALLOW)

    @staticmethod
    def _generate_formula(expr: SymbolicExpression, depth: FormulaDepth) -> str:
        """
        Generate formula with specified expansion depth.

        Args:
            expr: Expression to convert
            depth: Expansion depth (DEEP or SHALLOW)

        Returns:
            SMT-LIB2 formula string

        Raises:
            TypeError: If expression type is not supported
        """
        # Concolic object - expand or use concrete value
        if isinstance(expr, Concolic):
            return Predicate._handle_concolic(expr, depth)

        # String literal - return as-is
        if isinstance(expr, str):
            return expr

        # List/S-expression - recursively convert elements
        if isinstance(expr, list):
            return Predicate._handle_list(expr, depth)

        # Primitive types - convert to SMT-LIB2 literal
        if isinstance(expr, bool):
            return "true" if expr else "false"

        if isinstance(expr, int):
            return str(expr) if expr >= 0 else f"(- {-expr})"

        # Only float remains after Concolic, str, list, bool, and int checks
        return str(expr) if expr >= 0 else f"(- {-expr})"

    @staticmethod
    def _handle_concolic(expr: Concolic, depth: FormulaDepth) -> str:
        """
        Handle concolic object based on depth mode.

        Args:
            expr: Concolic object
            depth: Expansion depth

        Returns:
            Formula string (expression or concrete value)
        """
        if depth == FormulaDepth.DEEP:
            # Recursively expand the symbolic expression
            return Predicate._generate_formula(expr.expr, depth)
        else:
            # Use concrete value
            return expr.value

    @staticmethod
    def _handle_list(expr_list: list[Any], depth: FormulaDepth) -> str:
        """
        Convert list expression to S-expression string.

        Args:
            expr_list: List of expression elements
            depth: Expansion depth

        Returns:
            S-expression string like "(op arg1 arg2 ...)"
        """
        # Convert each element recursively
        elements = [Predicate._generate_formula(element, depth) for element in expr_list]

        # Join with spaces and wrap in parentheses
        return f"({' '.join(elements)})"


# ============================================================================
# Helper Functions
# ============================================================================


def create_predicate(expr: SymbolicExpression, value: bool) -> Predicate:
    """
    Factory function to create a predicate.

    Args:
        expr: Symbolic expression
        value: Boolean value

    Returns:
        New Predicate instance

    Examples:
        >>> pred = create_predicate(["<", "x", "10"], True)
        >>> pred.get_formula()
        "(assert (< x 10))"
    """
    return Predicate(expr, value)


def predicate_to_smt(pred: Predicate) -> str:
    """
    Convert predicate to SMT assertion.

    Args:
        pred: Predicate to convert

    Returns:
        SMT-LIB2 assertion string

    Examples:
        >>> pred = Predicate(["=", "x", "5"], True)
        >>> predicate_to_smt(pred)
        "(assert (= x 5))"
    """
    return pred.get_formula()
