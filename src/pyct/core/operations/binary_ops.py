from __future__ import annotations

from enum import Enum


class BinaryOp(Enum):
    """
    Binary operations supported by concolic numeric types.

    Each operation is defined by:
    - Python magic method name (e.g., "__add__")
    - SMT-LIB2 operator symbol (e.g., "+")
    """

    # Arithmetic operations
    ADD = ("__add__", "+")
    SUB = ("__sub__", "-")
    MUL = ("__mul__", "*")
    TRUEDIV = ("__truediv__", "/")
    FLOORDIV = ("__floordiv__", "div")
    MOD = ("__mod__", "mod")

    # Comparison operations
    EQ = ("__eq__", "=")
    NE = ("__ne__", "not_eq")  # Special handling needed
    LT = ("__lt__", "<")
    LE = ("__le__", "<=")
    GT = ("__gt__", ">")
    GE = ("__ge__", ">=")

    # Reverse arithmetic operations
    RADD = ("__radd__", "+")
    RSUB = ("__rsub__", "-")
    RMUL = ("__rmul__", "*")
    RTRUEDIV = ("__rtruediv__", "/")
    RFLOORDIV = ("__rfloordiv__", "div")
    RMOD = ("__rmod__", "mod")

    def __init__(self, method_name: str, smt_op: str):
        """
        Initialize binary operation.

        Args:
            method_name: Python magic method name
            smt_op: SMT-LIB2 operator symbol
        """
        self.method_name = method_name
        self.smt_op = smt_op

    @property
    def is_division(self) -> bool:
        """Check if this is a division operation."""
        return self in (
            BinaryOp.TRUEDIV,
            BinaryOp.FLOORDIV,
            BinaryOp.MOD,
            BinaryOp.RTRUEDIV,
            BinaryOp.RFLOORDIV,
            BinaryOp.RMOD,
        )

    @property
    def is_comparison(self) -> bool:
        """Check if this is a comparison operation."""
        return self in (
            BinaryOp.EQ,
            BinaryOp.NE,
            BinaryOp.LT,
            BinaryOp.LE,
            BinaryOp.GT,
            BinaryOp.GE,
        )

    @property
    def is_reverse(self) -> bool:
        """Check if this is a reverse operation."""
        return self.method_name.startswith("__r")

    def get_reverse_method(self) -> str:
        """
        Get the reverse operation method name.

        Returns:
            Method name for the reverse operation
        """
        reverse_map = {
            BinaryOp.ADD: "__radd__",
            BinaryOp.SUB: "__rsub__",
            BinaryOp.MUL: "__rmul__",
            BinaryOp.TRUEDIV: "__rtruediv__",
            BinaryOp.FLOORDIV: "__rfloordiv__",
            BinaryOp.MOD: "__rmod__",
            BinaryOp.LT: "__gt__",
            BinaryOp.LE: "__ge__",
            BinaryOp.GT: "__lt__",
            BinaryOp.GE: "__le__",
            BinaryOp.EQ: "__eq__",
            BinaryOp.NE: "__ne__",
        }
        return reverse_map.get(self, self.method_name)
