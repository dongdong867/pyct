from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pyct.core.str.helpers import (
    ensure_concolic_int,
    ensure_concolic_str,
)
from pyct.utils import concolic_converter
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.str.ops")


@dataclass(frozen=True)
class _ComparisonSpec:
    """Specification for a string comparison operation."""

    smt_op: str
    forward: str
    reverse_method: str
    reverse: bool


class StringBinaryOperations:
    """Handles binary operations on concolic strings."""

    def __init__(self, concolic_str: Any):
        self.concolic_str = concolic_str
        self.engine = concolic_str.engine

    def add(self, other: Any) -> ConcolicType:
        """String concatenation: self + other."""
        concrete = str.__add__(
            self.concolic_str,
            concolic_converter.unwrap_concolic(other),
        )
        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        return concolic_converter.wrap_concolic(
            concrete,
            ["str.++", self.concolic_str, other_str],
            self.engine,
        )

    def radd(self, other: Any) -> ConcolicType:
        """Reverse string concatenation: other + self."""
        concrete = str.__add__(
            concolic_converter.unwrap_concolic(other),
            self.concolic_str,
        )
        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        return concolic_converter.wrap_concolic(
            concrete,
            ["str.++", other_str, self.concolic_str],
            self.engine,
        )

    def contains(self, other: Any) -> ConcolicType:
        """Check containment: other in self."""
        concrete = str.__contains__(
            self.concolic_str,
            concolic_converter.unwrap_concolic(other),
        )
        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        return concolic_converter.wrap_concolic(
            concrete,
            ["str.contains", self.concolic_str, other_str],
            self.engine,
        )

    def eq(self, other: Any) -> ConcolicType:
        """Equality: self == other."""
        concrete = _safe_compare(self.concolic_str, other, "__eq__", "__eq__")
        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        return concolic_converter.wrap_concolic(
            concrete,
            ["=", self.concolic_str, other_str],
            self.engine,
        )

    def ne(self, other: Any) -> ConcolicType:
        """Inequality: self != other."""
        concrete = _safe_compare(self.concolic_str, other, "__ne__", "__ne__")
        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        return concolic_converter.wrap_concolic(
            concrete,
            ["not", ["=", self.concolic_str, other_str]],
            self.engine,
        )

    def lt(self, other: Any) -> ConcolicType:
        """Less than: self < other."""
        spec = _ComparisonSpec("<", "__lt__", "__gt__", reverse=False)
        return self._comparison(spec, other)

    def le(self, other: Any) -> ConcolicType:
        """Less than or equal: self <= other."""
        spec = _ComparisonSpec("<=", "__le__", "__ge__", reverse=False)
        return self._comparison(spec, other)

    def gt(self, other: Any) -> ConcolicType:
        """Greater than: self > other."""
        spec = _ComparisonSpec("<", "__gt__", "__lt__", reverse=True)
        return self._comparison(spec, other)

    def ge(self, other: Any) -> ConcolicType:
        """Greater than or equal: self >= other."""
        spec = _ComparisonSpec("<=", "__ge__", "__le__", reverse=True)
        return self._comparison(spec, other)

    def mul(self, other: Any) -> ConcolicType:
        """String repetition: self * n."""
        concrete = _safe_compare(self.concolic_str, other, "__mul__", "__rmul__")

        if not isinstance(other, (bool, int)):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        count = ensure_concolic_int(other, self.engine)
        result = _build_repetition(self.concolic_str, count, self.engine)
        return concolic_converter.wrap_concolic(concrete, result, self.engine)

    def _comparison(self, spec: _ComparisonSpec, other: Any) -> ConcolicType:
        """Handle string comparisons (symbolic only for alphanumeric strings)."""
        concrete = _safe_compare(self.concolic_str, other, spec.forward, spec.reverse_method)

        if not isinstance(other, str):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        if not _both_alphanumeric(self.concolic_str, other):
            return concolic_converter.wrap_concolic(concrete, None, self.engine)

        other_str = ensure_concolic_str(other, self.engine)
        if spec.reverse:
            left, right = other_str, self.concolic_str
        else:
            left, right = self.concolic_str, other_str

        return concolic_converter.wrap_concolic(
            concrete,
            [f"str.{spec.smt_op}", left, right],
            self.engine,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_compare(concolic_str: Any, other: Any, forward: str, reverse: str) -> Any:
    """Compute concrete result with forward/reverse fallback."""
    try:
        return getattr(str, forward)(
            concolic_str,
            concolic_converter.unwrap_concolic(other),
        )
    except Exception:
        return getattr(concolic_converter.unwrap_concolic(other), reverse)(
            concolic_converter.unwrap_concolic(concolic_str),
        )


def _both_alphanumeric(concolic_str: Any, other: Any) -> bool:
    """Check if both strings are alphanumeric (needed for valid SMT comparison)."""
    return str.isalnum(concolic_str) and str.isalnum(concolic_converter.unwrap_concolic(other))


def _build_repetition(concolic_str: Any, count: Any, engine: Any) -> Any:
    """Build repeated concatenation expression: str * count."""
    result = concolic_converter.wrap_concolic("", None, engine)
    remaining = count

    while concolic_converter.unwrap_concolic(remaining) > 0:
        result_concrete = concolic_converter.unwrap_concolic(
            result
        ) + concolic_converter.unwrap_concolic(concolic_str)
        result = concolic_converter.wrap_concolic(
            result_concrete,
            ["str.++", result, concolic_str],
            engine,
        )
        remaining = concolic_converter.wrap_concolic(
            concolic_converter.unwrap_concolic(remaining) - 1,
            ["-", remaining, "1"],
            engine,
        )

    return result
