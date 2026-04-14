# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import logging
from typing import Any

from pyct.core import Concolic, MetaFinal
from pyct.utils import concolic_converter
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.float")


class ConcolicFloat(float, Concolic, metaclass=MetaFinal):
    """
    A float value that tracks both concrete and symbolic representations.

    ConcolicFloat inherits from float for compatibility while providing
    symbolic execution capabilities. It tracks both the actual float value
    and its symbolic expression.

    Type Conversions:
    - Standard conversions return primitives: float(), int(), bool()
    - Concolic conversions preserve symbolic tracking: to_float(), to_int()

    Examples:
        >>> cf = ConcolicFloat(3.14, "x", engine)
        >>> float(cf)  # Returns primitive: 3.14
        >>> cf.to_int()  # Returns ConcolicInt with tracking
        >>> cf >= 2.0  # Returns ConcolicBool with symbolic comparison
    """

    def __new__(
        cls,
        value: Any,
        expr: Any | None = None,
        engine: Any | None = None,
    ) -> ConcolicFloat:
        """
        Create a new ConcolicFloat instance.

        Args:
            value: Concrete float value
            expr: Symbolic expression
            engine: Concolic execution engine

        Returns:
            New ConcolicFloat instance

        Raises:
            TypeError: If value cannot be converted to float
        """
        # Validate and convert to float
        if not isinstance(value, float):
            try:
                value = float(value)
            except (ValueError, TypeError) as e:
                raise TypeError(f"Cannot convert {type(value).__name__} to float: {e}")

        instance = float.__new__(cls, value)
        return instance

    def __init__(
        self,
        value: Any,
        expr: Any | None = None,
        engine: Any | None = None,
    ) -> None:
        """Initialize concolic attributes."""
        super().__init__(expr=expr, engine=engine)

    # ========================================================================
    # Comparison Operations
    # ========================================================================

    def __ge__(self, other: Any) -> ConcolicType:
        """
        Greater than or equal comparison with symbolic tracking.

        Args:
            other: Value to compare with

        Returns:
            ConcolicBool representing the comparison result

        Examples:
            >>> cf = ConcolicFloat(3.14, "x", engine)
            >>> result = cf >= 2.0
            >>> result.expr
            [">=", cf, ConcolicFloat(2.0)]
        """
        # Compute concrete result
        concrete = self._compute_comparison(other, "__ge__", "__le__")

        # Prepare symbolic operand
        symbolic_other = self._to_symbolic_float(other)

        # Handle incompatible types (return concrete only)
        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        # Build symbolic expression
        symbolic_expr = [">=", self, symbolic_other]

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __lt__(self, other: Any) -> ConcolicType:
        """Less than comparison with symbolic tracking."""
        concrete = self._compute_comparison(other, "__lt__", "__gt__")
        symbolic_other = self._to_symbolic_float(other)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        symbolic_expr = ["<", self, symbolic_other]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __le__(self, other: Any) -> ConcolicType:
        """Less than or equal comparison with symbolic tracking."""
        concrete = self._compute_comparison(other, "__le__", "__ge__")
        symbolic_other = self._to_symbolic_float(other)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        symbolic_expr = ["<=", self, symbolic_other]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __gt__(self, other: Any) -> ConcolicType:
        """Greater than comparison with symbolic tracking."""
        concrete = self._compute_comparison(other, "__gt__", "__lt__")
        symbolic_other = self._to_symbolic_float(other)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        symbolic_expr = [">", self, symbolic_other]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __eq__(self, other: Any) -> ConcolicType:
        """Equality comparison with symbolic tracking."""
        concrete = self._compute_comparison(other, "__eq__", "__eq__")
        symbolic_other = self._to_symbolic_float(other)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        symbolic_expr = ["=", self, symbolic_other]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __ne__(self, other: Any) -> ConcolicType:
        """Not equal comparison with symbolic tracking."""
        concrete = self._compute_comparison(other, "__ne__", "__ne__")
        symbolic_other = self._to_symbolic_float(other)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        symbolic_expr = ["not", ["=", self, symbolic_other]]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def _compute_comparison(self, other: Any, forward_op: str, reverse_op: str) -> bool:
        """
        Compute concrete comparison result with fallback to reverse operation.

        Args:
            other: Value to compare with
            forward_op: Forward comparison operator (e.g., "__ge__")
            reverse_op: Reverse comparison operator (e.g., "__le__")

        Returns:
            Concrete boolean result
        """
        try:
            # Try forward comparison: self >= other
            result = getattr(float, forward_op)(self, concolic_converter.unwrap_concolic(other))
            if result is not NotImplemented:
                return result
        except (TypeError, AttributeError):
            pass

        # Fallback to reverse comparison: other <= self
        try:
            return getattr(concolic_converter.unwrap_concolic(other), reverse_op)(
                concolic_converter.unwrap_concolic(self)
            )
        except (TypeError, AttributeError) as e:
            raise TypeError(
                f"Cannot compare {type(self).__name__} with {type(other).__name__}: {e}"
            )

    def _to_symbolic_float(self, value: Any) -> ConcolicFloat | None:
        """
        Convert value to symbolic float for operations.

        Args:
            value: Value to convert

        Returns:
            ConcolicFloat instance, or None if conversion not supported

        Note:
            Returns None for incompatible types like str or range to discard
            symbolic expression when it cannot match the concrete value.
        """
        # Already a Concolic object
        if isinstance(value, Concolic):
            # Convert bool to float if needed
            if hasattr(value, "to_float"):
                return value.to_float()
            # Direct use if already float-compatible
            return value

        # Primitive types
        value_type = type(value)

        # Boolean: convert to float (True=1.0, False=0.0)
        if value_type is bool:
            return self.__class__(float(value), None, self.engine)

        # Numeric types: int or float
        if value_type in (int, float):
            return self.__class__(float(value), None, self.engine)

        # Incompatible types: str, range, etc.
        # Return None to signal "discard symbolic expression"
        log.debug("Incompatible type for float comparison: %s", value_type.__name__)
        return None

    # ========================================================================
    # Arithmetic Operations
    # ========================================================================

    def __truediv__(self, other: Any) -> ConcolicType:
        """
        Division operation with symbolic tracking.

        Args:
            other: Divisor

        Returns:
            ConcolicFloat representing the division result

        Examples:
            >>> cf = ConcolicFloat(10.0, "x", engine)
            >>> result = cf / 2.0
            >>> result.expr
            ["/", cf, ConcolicFloat(2.0)]
        """
        # Compute concrete result
        concrete = float.__truediv__(self, concolic_converter.unwrap_concolic(other))

        # Prepare symbolic operand
        symbolic_other = self._to_symbolic_float_for_arithmetic(other)

        # Build symbolic expression
        symbolic_expr = ["/", self, symbolic_other]

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def _to_symbolic_float_for_arithmetic(self, value: Any) -> ConcolicFloat:
        """
        Convert value to symbolic float for arithmetic operations.

        Args:
            value: Value to convert

        Returns:
            ConcolicFloat instance

        Note:
            Uses 1.0 as fallback for unconvertible types to avoid division errors.
        """
        # Already a Concolic object
        if isinstance(value, Concolic):
            if hasattr(value, "to_float"):
                return value.to_float()
            return value

        # Try to convert to float
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            # Fallback to 1.0 to avoid division errors in symbolic execution
            log.warning("Cannot convert %s to float, using 1.0", type(value).__name__)
            float_value = 1.0

        return self.__class__(float_value, None, self.engine)

    # ========================================================================
    # Type Conversions
    # ========================================================================

    def to_float(self) -> ConcolicFloat:
        """
        Convert to ConcolicFloat (identity).

        Returns:
            Self (already a ConcolicFloat)
        """
        return self

    def to_int(self) -> ConcolicType:
        """
        Convert to ConcolicInt, preserving symbolic tracking.

        Note:
            Python's int() truncates towards zero: int(-2.5) == -2
            SMT's to_int rounds towards negative infinity: (to_int -2.5) == -3

            This method adjusts the SMT formula to match Python's behavior.

        Returns:
            ConcolicInt with adjusted symbolic expression

        Examples:
            >>> cf = ConcolicFloat(-2.5, "x", engine)
            >>> ci = cf.to_int()
            >>> int(cf)  # Primitive: -2
            >>> ci.expr  # Adjusted for Python semantics
            ["+", ["to_int", cf], ["ite", ["and", ["<", cf, "0"], ["not", ["is_int", cf]]], "1", "0"]]
        """  # noqa: E501
        # Compute concrete result (Python truncation)
        concrete = int(self)

        # Build adjusted symbolic expression
        # SMT's to_int rounds down, so we need to adjust for negative non-integers
        symbolic_expr = self._build_int_conversion_expr()

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def _build_int_conversion_expr(self) -> list:
        """
        Build symbolic expression for int conversion.

        Adjusts SMT's to_int (floor) to match Python's int() (truncate).

        Returns:
            Symbolic expression for conversion
        """
        # For negative non-integers, add 1 to match Python's truncation
        # (to_int -2.5) gives -3, but Python int(-2.5) gives -2
        return [
            "+",
            ["to_int", self],
            [
                "ite",
                ["and", ["<", self, "0"], ["not", ["is_int", self]]],
                "1",
                "0",
            ],
        ]

    # ========================================================================
    # Standard Python Conversions
    # ========================================================================

    def __float__(self) -> float:
        """Convert to primitive float."""
        return float.__float__(self)

    def __int__(self) -> int:
        """Convert to primitive int."""
        return float.__int__(self)

    def __bool__(self) -> bool:
        """Convert to primitive bool."""
        return float.__bool__(self)

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return f"ConcolicFloat({concolic_converter.unwrap_concolic(self)})"


# ============================================================================
# Helper Functions
# ============================================================================


def create_concolic_float(
    value: float, expr: Any | None = None, engine: Any | None = None
) -> ConcolicFloat:
    """
    Factory function to create a ConcolicFloat.

    Args:
        value: Concrete float value
        expr: Symbolic expression
        engine: Concolic execution engine

    Returns:
        New ConcolicFloat instance

    Examples:
        >>> cf = create_concolic_float(3.14, "x", engine)
        >>> cf >= 2.0
    """
    return ConcolicFloat(value, expr, engine)
