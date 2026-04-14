from __future__ import annotations

import logging
from typing import Any

from pyct.core.str.helpers import CaseConverter, ensure_concolic_str
from pyct.utils.concolic_converter import unwrap_concolic, wrap_concolic

log = logging.getLogger("ct.con.str.transform")


class StringTransformation:
    """String transformation operations."""

    @staticmethod
    def lower(concolic_str: Any) -> Any:
        """Convert to lowercase."""
        return CaseConverter.to_lower(concolic_str)

    @staticmethod
    def upper(concolic_str: Any) -> Any:
        """Convert to uppercase."""
        return CaseConverter.to_upper(concolic_str)

    @staticmethod
    def lstrip(concolic_str: Any, chars: Any = None) -> Any:
        """Remove leading characters."""
        concrete = str.lstrip(concolic_str, unwrap_concolic(chars))
        chars = _normalize_strip_chars(chars)
        expr = _build_strip_expression(
            concolic_str,
            chars,
            direction="prefix",
        )
        return wrap_concolic(concrete, expr, concolic_str.engine)

    @staticmethod
    def rstrip(concolic_str: Any, chars: Any = None) -> Any:
        """Remove trailing characters."""
        concrete = str.rstrip(concolic_str, unwrap_concolic(chars))
        chars = _normalize_strip_chars(chars)
        expr = _build_strip_expression(
            concolic_str,
            chars,
            direction="suffix",
        )
        return wrap_concolic(concrete, expr, concolic_str.engine)


def _normalize_strip_chars(chars: Any) -> str:
    """Default to whitespace if no chars specified."""
    if chars is None or not isinstance(chars, str):
        return " "
    return chars


def _build_strip_expression(
    concolic_str: Any,
    chars: str,
    direction: str,
) -> Any:
    """Build an iterative ITE expression that strips leading or trailing chars.

    Args:
        direction: "prefix" for lstrip, "suffix" for rstrip.
    """
    expr = concolic_str
    test_str = str(unwrap_concolic(concolic_str))
    check_fn = str.startswith if direction == "prefix" else str.endswith

    while any(check_fn(test_str, ch) for ch in chars):
        test_str = test_str[1:] if direction == "prefix" else test_str[:-1]
        condition = _build_char_condition(chars, expr, concolic_str.engine, direction)
        remainder = _strip_one_char(expr, direction)
        expr = ["ite", condition, remainder, expr]

    return expr


def _build_char_condition(
    chars: str,
    expr: Any,
    engine: Any,
    direction: str,
) -> Any:
    """Build an OR condition checking if any char matches at the edge."""
    smt_op = "str.prefixof" if direction == "prefix" else "str.suffixof"
    conditions = [[smt_op, ensure_concolic_str(ch, engine), expr] for ch in chars]
    if len(conditions) == 1:
        return conditions[0]
    return ["or"] + conditions


def _strip_one_char(expr: Any, direction: str) -> list:
    """Build SMT expression that removes one char from the given end."""
    if direction == "prefix":
        return ["str.substr", expr, "1", ["str.len", expr]]
    return ["str.substr", expr, "0", ["-", ["str.len", expr], "1"]]
