from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class BooleanConverter:
    """Handles boolean type conversions."""

    # Standard boolean representations as integers
    FALSE_AS_INT = 0
    TRUE_AS_INT = 1

    @classmethod
    def normalize_to_bool(cls, value: Any) -> bool:
        """
        Normalize any value to a proper boolean.

        Args:
            value: Value to normalize (can be int, bool, or other)

        Returns:
            Normalized boolean value

        Raises:
            TypeError: If value cannot be converted to boolean

        Examples:
            >>> BooleanConverter.normalize_to_bool(0)
            False
            >>> BooleanConverter.normalize_to_bool(1)
            True
            >>> BooleanConverter.normalize_to_bool(True)
            True
        """
        # Handle integer representations
        if value == cls.FALSE_AS_INT:
            return False
        if value == cls.TRUE_AS_INT:
            return True

        # Handle boolean values
        if isinstance(value, bool):
            return value

        # Try to convert other types
        try:
            return bool(value)
        except Exception as e:
            raise TypeError(f"Cannot convert {type(value).__name__} to bool: {e}")

    @classmethod
    def to_concolic_bool(cls, value: Any, concolic_class: type[T], engine: Any = None) -> T:
        """
        Convert value to ConcolicBool instance.

        Args:
            value: Value to convert
            concolic_class: ConcolicBool class to instantiate
            engine: Optional concolic engine

        Returns:
            ConcolicBool instance

        Examples:
            >>> converter = BooleanConverter()
            >>> cb = converter.to_concolic_bool(1, ConcolicBool)
            >>> cb
            ConcolicBool(True)
        """
        try:
            bool_value = bool(value)
        except Exception:
            bool_value = False

        return concolic_class(bool_value, None, engine)


class NumericConverter:
    """Handles numeric type conversions."""

    @staticmethod
    def bool_to_int(value: bool) -> int:
        """Convert boolean to integer (True=1, False=0)."""
        return 1 if value else 0

    @staticmethod
    def bool_to_float(value: bool) -> float:
        """Convert boolean to float (True=1.0, False=0.0)."""
        return 1.0 if value else 0.0
