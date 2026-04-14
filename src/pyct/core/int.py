# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import logging
from typing import Any, Optional

from pyct.core import Concolic, MetaFinal
from pyct.core.operations.binary_ops import BinaryOp
from pyct.core.operations.handlers import BinaryOperationHandler
from pyct.utils import concolic_converter
from pyct.utils.smt_converter import py2smt
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.int")


def _concrete_only(primitive_method, self, other):
    """Execute a binary operation without symbolic tracking."""
    return concolic_converter.wrap_concolic(
        primitive_method(self, concolic_converter.unwrap_concolic(other)),
        None,
        self.engine,
    )


def _rounding_identity(primitive_method, self, *args, **kwargs):
    """Rounding on an integer returns itself (ceil, floor, round, trunc)."""
    args = [concolic_converter.unwrap_concolic(a) for a in args]
    kwargs = {k: concolic_converter.unwrap_concolic(v) for k, v in kwargs.items()}
    concrete = primitive_method(self, *args, **kwargs)
    return concolic_converter.wrap_concolic(concrete, self, self.engine)


class ConcolicInt(int, Concolic, metaclass=MetaFinal):
    """An integer that tracks both concrete and symbolic representations."""

    def __new__(
        cls,
        value: Any,
        expr: Optional[Any] = None,
        engine: Optional[Any] = None,
    ) -> ConcolicInt:
        if not isinstance(value, int) or isinstance(value, bool):
            value = int(value)
        return int.__new__(cls, value)

    def __init__(
        self,
        value: Any,
        expr: Optional[Any] = None,
        engine: Optional[Any] = None,
    ) -> None:
        super().__init__(expr=expr, engine=engine)
        if log.isEnabledFor(logging.DEBUG):
            log.debug("ConcolicInt created: value=%d, expr=%s", int(self), self.expr)

    # -- Unary operations --

    def __abs__(self) -> "ConcolicType":
        return concolic_converter.wrap_concolic(
            int.__abs__(self), ["abs", self], self.engine
        )

    def __neg__(self) -> "ConcolicType":
        return concolic_converter.wrap_concolic(
            int.__neg__(self), ["-", self], self.engine
        )

    def __pos__(self) -> "ConcolicType":
        return concolic_converter.wrap_concolic(int.__pos__(self), self, self.engine)

    # -- Binary arithmetic --

    def __add__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.ADD, other)

    def __sub__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.SUB, other)

    def __mul__(self, other: Any) -> "ConcolicType":
        if isinstance(concolic_converter.unwrap_concolic(other), str):
            return concolic_converter.wrap_concolic(other).__mul__(self)
        return BinaryOperationHandler(self).execute(BinaryOp.MUL, other)

    def __truediv__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.TRUEDIV, other)

    def __floordiv__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.FLOORDIV, other)

    def __mod__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.MOD, other)

    # -- Reverse arithmetic --

    def __radd__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(
            BinaryOp.RADD, other, is_reverse=True
        )

    def __rsub__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(
            BinaryOp.RSUB, other, is_reverse=True
        )

    def __rmul__(self, other: Any) -> "ConcolicType":
        if isinstance(other, (str, Concolic)) and isinstance(
            concolic_converter.unwrap_concolic(other),
            str,
        ):
            return concolic_converter.wrap_concolic(other).__mul__(self)
        return BinaryOperationHandler(self).execute(
            BinaryOp.RMUL, other, is_reverse=True
        )

    def __rtruediv__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(
            BinaryOp.RTRUEDIV, other, is_reverse=True
        )

    def __rfloordiv__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(
            BinaryOp.RFLOORDIV, other, is_reverse=True
        )

    def __rmod__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(
            BinaryOp.RMOD, other, is_reverse=True
        )

    # -- Comparisons --

    def __eq__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.EQ, other)

    def __ne__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.NE, other)

    def __lt__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.LT, other)

    def __le__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.LE, other)

    def __gt__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.GT, other)

    def __ge__(self, other: Any) -> "ConcolicType":
        return BinaryOperationHandler(self).execute(BinaryOp.GE, other)

    # -- Bitwise (concrete only, no symbolic tracking) --

    def __and__(self, other: Any) -> "ConcolicType":
        return _concrete_only(int.__and__, self, other)

    def __or__(self, other: Any) -> "ConcolicType":
        return _concrete_only(int.__or__, self, other)

    def __xor__(self, other: Any) -> "ConcolicType":
        return _concrete_only(int.__xor__, self, other)

    def __lshift__(self, other: Any) -> "ConcolicType":
        return _concrete_only(int.__lshift__, self, other)

    def __rshift__(self, other: Any) -> "ConcolicType":
        return _concrete_only(int.__rshift__, self, other)

    def __invert__(self) -> "ConcolicType":
        return concolic_converter.wrap_concolic(int.__invert__(self), None, self.engine)

    # -- Boolean and special --

    def __bool__(self) -> bool:
        """Return self != 0, registering branch for symbolic execution."""
        concrete = int.__bool__(self)
        symbolic_expr = ["not", ["=", self, "0"]]
        concolic_converter.wrap_concolic(
            concrete, symbolic_expr, self.engine
        ).__bool__()
        return concrete

    def __hash__(self) -> int:
        return int.__hash__(self)

    def __index__(self) -> int:
        return int.__index__(self)

    # -- Rounding (identity for integers) --

    def __ceil__(self, *args, **kwargs) -> "ConcolicType":
        return _rounding_identity(int.__ceil__, self, *args, **kwargs)

    def __floor__(self, *args, **kwargs) -> "ConcolicType":
        return _rounding_identity(int.__floor__, self, *args, **kwargs)

    def __round__(self, *args, **kwargs) -> "ConcolicType":
        return _rounding_identity(int.__round__, self, *args, **kwargs)

    def __trunc__(self, *args, **kwargs) -> "ConcolicType":
        return _rounding_identity(int.__trunc__, self, *args, **kwargs)

    # -- Type conversions --

    def to_bool(self) -> "ConcolicType":
        concrete = int.__bool__(self)
        return concolic_converter.wrap_concolic(
            concrete, ["not", ["=", self, "0"]], self.engine
        )

    def to_int(self) -> ConcolicInt:
        return self

    def to_float(self) -> "ConcolicType":
        return concolic_converter.wrap_concolic(
            int.__float__(self), ["to_real", self], self.engine
        )

    def to_str(self) -> "ConcolicType":
        concrete = int.__str__(self)
        expr = [
            "ite",
            ["<", self, "0"],
            ["str.++", py2smt("-"), ["int.to.str", ["-", self]]],
            ["int.to.str", self],
        ]
        return concolic_converter.wrap_concolic(concrete, expr, self.engine)

    def __repr__(self) -> str:
        return f"ConcolicInt({concolic_converter.unwrap_concolic(self)})"
