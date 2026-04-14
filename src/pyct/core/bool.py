# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import logging
from typing import Any

from pyct.core import Concolic, MetaFinal
from pyct.core.expressions import BooleanExpressionBuilder as BoolExpr
from pyct.core.type_conversion import BooleanConverter, NumericConverter
from pyct.utils import concolic_converter
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.bool")


class ConcolicBool(int, Concolic, metaclass=MetaFinal):
    """
    A boolean value that tracks both concrete and symbolic representations.

    Type Conversions:
    - Standard conversions return primitives: bool(), int(), float(), str()
    - Concolic conversions preserve symbolic tracking: to_bool(), to_int(), to_float()

    Examples:
        >>> cb = ConcolicBool(True, "x", engine)
        >>> bool(cb)  # Returns primitive bool: True
        >>> cb.to_int()  # Returns ConcolicInt with tracking
    """

    def __new__(
        cls,
        value: Any,
        expr: Any | None = None,
        engine: Any | None = None,
    ) -> ConcolicBool:
        """Create a new ConcolicBool instance."""
        normalized = BooleanConverter.normalize_to_bool(value)
        instance = int.__new__(cls, normalized)
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
    # Standard Python Type Conversions (return primitives)
    # ========================================================================

    def __bool__(self) -> bool:
        """
        Convert to primitive boolean (standard Python protocol).

        This also registers the branch for symbolic execution.

        Returns:
            Primitive bool (True or False)
        """
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "ConcolicBool.__bool__ called: %s",
                bool(concolic_converter.unwrap_concolic(self)),
            )

        self._register_branch()
        return int.__bool__(self)

    def __int__(self) -> int:
        """
        Convert to primitive integer (standard Python protocol).

        Returns:
            Primitive int (0 or 1)
        """
        return int.__int__(self)

    def __float__(self) -> float:
        """
        Convert to primitive float (standard Python protocol).

        Returns:
            Primitive float (0.0 or 1.0)
        """
        return float(int.__int__(self))

    def __str__(self) -> str:
        """
        Convert to string (standard Python protocol).

        Returns:
            Primitive string ("True" or "False")
        """
        return str(bool(self))

    # ========================================================================
    # Concolic Type Conversions (preserve symbolic tracking)
    # ========================================================================

    def to_bool(self) -> ConcolicBool:
        """
        Convert to ConcolicBool (identity for ConcolicBool).

        This method exists for API consistency with other concolic types.

        Returns:
            Self (already a ConcolicBool)

        Examples:
            >>> cb = ConcolicBool(True, "x", engine)
            >>> cb.to_bool() is cb
            True
        """
        return self

    def to_int(self) -> ConcolicType:
        """
        Convert to ConcolicInt, preserving symbolic tracking.

        Returns:
            concolic_converter.wrap_concolic wrapping the integer value (0 or 1) with symbolic \
            expression

        Examples:
            >>> cb = ConcolicBool(True, "x", engine)
            >>> ci = cb.to_int()
            >>> ci.concrete
            1
            >>> ci.expr
            ["ite", cb, "1", "0"]
        """
        concrete = NumericConverter.bool_to_int(concolic_converter.unwrap_concolic(self))
        symbolic_expr = BoolExpr.if_then_else(self, "1", "0")

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def to_float(self) -> ConcolicType:
        """
        Convert to ConcolicFloat, preserving symbolic tracking.

        Returns:
            concolic_converter.wrap_concolic wrapping the float value (0.0 or 1.0) with symbolic \
            expression

        Examples:
            >>> cb = ConcolicBool(True, "x", engine)
            >>> cf = cb.to_float()
            >>> cf.concrete
            1.0
            >>> cf.expr
            ["ite", cb, "1.0", "0.0"]
        """
        concrete = NumericConverter.bool_to_float(concolic_converter.unwrap_concolic(self))
        symbolic_expr = BoolExpr.if_then_else(self, "1.0", "0.0")

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def to_str(self) -> str:
        """
        Convert to string representation.

        Note: Strings are not tracked symbolically in this implementation,
        so this returns a primitive string.

        Returns:
            String representation ("True" or "False")
        """
        return str(concolic_converter.unwrap_concolic(self))

    # ========================================================================
    # Core Boolean Operations
    # ========================================================================

    def _register_branch(self) -> None:
        """Register this boolean decision as a branch point."""
        if self.engine and hasattr(self.engine, "path"):
            self.engine.path.add_branch(self, self.engine.constraints_to_solve)

    def __xor__(self, other: Any) -> ConcolicType:
        """XOR operation with symbolic expression tracking."""
        concrete = self._compute_xor(other)
        symbolic_other = self._to_concolic_bool(other)
        symbolic_expr = BoolExpr.xor(self, symbolic_other)

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def _compute_xor(self, other: Any) -> bool:
        """Compute concrete XOR result."""
        return (bool(concolic_converter.unwrap_concolic(self))).__xor__(
            concolic_converter.unwrap_concolic(other)
        )

    def _to_concolic_bool(self, value: Any) -> ConcolicBool:
        """Convert value to ConcolicBool for operations."""
        if isinstance(value, Concolic):
            # If it's already concolic, convert to bool
            if hasattr(value, "to_bool"):
                return value.to_bool()
            # Fallback: wrap the boolean value
            return BooleanConverter.to_concolic_bool(bool(value), self.__class__, self.engine)

        return BooleanConverter.to_concolic_bool(value, self.__class__, self.engine)

    def __add__(self, other: Any) -> int | Any:
        """Addition operation, delegating to other if it's Concolic."""
        # TODO: - update this to fit int and str type
        # if isinstance(other, Concolic):
        #     return other.__radd__(self)
        return super().__add__(other)

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return f"ConcolicBool({concolic_converter.unwrap_concolic(self)})"
