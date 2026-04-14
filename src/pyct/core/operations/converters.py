from __future__ import annotations

import logging
from typing import Any, Optional

from pyct.core import Concolic
from pyct.utils import concolic_converter

log = logging.getLogger("ct.con.converters")


class OperandConverter:
    """Converts operands to appropriate concolic types for operations."""

    @staticmethod
    def to_concolic_numeric(
        value: Any,
        target_class: type,
        engine: Any = None,
        allow_float: bool = True,
    ) -> Optional[Any]:
        """
        Convert value to concolic numeric type.

        Args:
            value: Value to convert
            target_class: Target concolic class (ConcolicInt, ConcolicFloat)
            engine: Concolic execution engine
            allow_float: Whether to allow float values (for mixed operations)

        Returns:
            Concolic object or None if conversion not supported

        Examples:
            >>> converter = OperandConverter()
            >>> ci = converter.to_concolic_numeric(42, ConcolicInt, engine)
            >>> ci
            ConcolicInt(42)
        """
        # Already concolic
        if isinstance(value, Concolic):
            return OperandConverter._convert_concolic(value, target_class)

        # Primitive types
        value_type = type(value)

        # Boolean: convert to int
        if value_type is bool:
            int_value = int(value)
            return target_class(int_value, None, engine)

        # Integer
        if value_type is int:
            return target_class(value, None, engine)

        # Float
        if value_type is float:
            if allow_float:
                return concolic_converter.wrap_concolic(value, None, engine)
            return None

        # Incompatible types
        log.debug("Cannot convert %s to concolic numeric", value_type.__name__)
        return None

    @staticmethod
    def _convert_concolic(value: Concolic, target_class: type) -> Any:
        """
        Convert concolic object to target type.

        Args:
            value: Concolic object to convert
            target_class: Target concolic class

        Returns:
            Converted concolic object
        """
        # Check for conversion method
        if target_class.__name__ == "ConcolicInt" and hasattr(value, "to_int"):
            return value.to_int()  # type: ignore
        elif target_class.__name__ == "ConcolicFloat" and hasattr(value, "to_float"):
            return value.to_float()  # type: ignore
        elif target_class.__name__ == "ConcolicBool" and hasattr(value, "to_bool"):
            return value.to_bool()  # type: ignore

        # Return as-is if already compatible
        return value

    @staticmethod
    def validate_for_floor_division(value: Any) -> bool:
        """
        Validate operand for floor division.

        Args:
            value: Operand to validate

        Returns:
            True if valid for floor division

        Note:
            Floor division has restrictions:
            - No float operands (not supported in SMT)
            - No negative divisors (not currently supported)
        """
        # Check for float
        if isinstance(value, float):
            log.debug("Floor division with float not supported in SMT")
            return False

        # Check for negative integer
        if isinstance(value, int) and concolic_converter.unwrap_concolic(value) < 0:
            log.debug("Negative divisor not currently supported")
            return False

        return True
