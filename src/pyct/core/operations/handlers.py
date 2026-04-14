from __future__ import annotations

import contextlib
import logging
from typing import Any

from pyct.core.operations.binary_ops import BinaryOp
from pyct.core.operations.converters import OperandConverter
from pyct.utils import concolic_converter
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.handlers")


class BinaryOperationHandler:
    """Handles binary operations with symbolic tracking."""

    def __init__(self, concolic_obj: Any):
        self.concolic_obj = concolic_obj
        self.converter = OperandConverter()

    def execute(
        self,
        op: BinaryOp,
        other: Any,
        is_reverse: bool = False,
    ) -> ConcolicType:
        """Execute binary operation with symbolic tracking."""
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "%s.%s called with other=%r",
                type(self.concolic_obj).__name__,
                op.method_name,
                other,
            )

        if op.is_division and not is_reverse:
            self._check_division_by_zero(other)

        concrete = self._compute_concrete(op, other, is_reverse)
        symbolic_other = self._prepare_operand(other, op)

        if symbolic_other is None:
            return concolic_converter.wrap_concolic(
                concrete,
                None,
                self.concolic_obj.engine,
            )

        symbolic_expr = self._build_expression(op, symbolic_other, is_reverse)
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            self.concolic_obj.engine,
        )

    def _compute_concrete(self, op: BinaryOp, other: Any, _is_reverse: bool) -> Any:
        """Compute concrete result using the primitive type's method."""
        primitive_type = _find_primitive_type(type(self.concolic_obj))
        unwrapped_other = concolic_converter.unwrap_concolic(other)

        result = _try_forward_operation(primitive_type, op, self.concolic_obj, unwrapped_other)
        if result is not NotImplemented:
            return result

        return _try_reverse_operation(op, self.concolic_obj, unwrapped_other)

    def _prepare_operand(self, value: Any, op: BinaryOp) -> Any | None:
        """Convert operand to a concolic type for symbolic computation."""
        symbolic = self.converter.to_concolic_numeric(
            value,
            self.concolic_obj.__class__,
            self.concolic_obj.engine,
            allow_float=True,
        )

        if (
            symbolic is not None
            and op
            in (
                BinaryOp.FLOORDIV,
                BinaryOp.MOD,
                BinaryOp.RFLOORDIV,
                BinaryOp.RMOD,
            )
            and not self.converter.validate_for_floor_division(symbolic)
        ):
            return None

        return symbolic

    def _build_expression(self, op: BinaryOp, other: Any, is_reverse: bool) -> list:
        """Build symbolic S-expression for the operation."""
        if is_reverse:
            left, right = other, self.concolic_obj
        else:
            left, right = self.concolic_obj, other

        if op == BinaryOp.NE:
            return ["not", ["=", left, right]]

        return [op.smt_op, left, right]

    def _check_division_by_zero(self, other: Any) -> None:
        """Insert a symbolic branch check for division by zero."""
        with contextlib.suppress(Exception):
            (other != 0).__bool__()


# ---------------------------------------------------------------------------
# Helpers for _compute_concrete
# ---------------------------------------------------------------------------


def _find_primitive_type(concolic_type: type) -> type:
    """Walk the MRO to find the underlying primitive type (int/float/str/bool)."""
    primitive_names = ("int", "float", "str", "bool")
    for base in concolic_type.__mro__[1:]:
        if base.__name__ in primitive_names:
            return base
    return concolic_type.__mro__[1]


def _try_forward_operation(
    primitive_type: type,
    op: BinaryOp,
    concolic_obj: Any,
    unwrapped_other: Any,
) -> Any:
    """Try the forward method (e.g. int.__add__) on the primitive type."""
    try:
        method = getattr(primitive_type, op.method_name)
        return method(concolic_obj, unwrapped_other)
    except (TypeError, AttributeError):
        return NotImplemented


def _try_reverse_operation(
    op: BinaryOp,
    concolic_obj: Any,
    unwrapped_other: Any,
) -> Any:
    """Fall back to the reverse method on the other operand."""
    reverse_method = op.get_reverse_method()
    try:
        return getattr(unwrapped_other, reverse_method)(
            concolic_converter.unwrap_concolic(concolic_obj),
        )
    except Exception as e:
        raise TypeError(
            f"Cannot perform {op.method_name} between "
            + f"{type(concolic_obj).__name__} and "
            + f"{type(unwrapped_other).__name__}: {e}"
        ) from e
