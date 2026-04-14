from __future__ import annotations

from typing import Any

from pyct.utils import concolic_converter
from pyct.utils.smt_converter import py2smt


class SubstringHelper:
    """Helper for substring operations."""

    @staticmethod
    def substr(concolic_str: Any, start: Any = None, end: Any = None) -> Any:
        """Extract substring with symbolic tracking."""
        start, end = _default_bounds(concolic_str, start, end)
        concrete = _compute_concrete_slice(concolic_str, start, end)

        start_n = _normalize_index(start, concolic_str)
        end_n = _normalize_index(end, concolic_str)

        if _is_full_string(start_n, end_n, concolic_str):
            return concolic_str

        return _build_substr_expression(concolic_str, start_n, end_n, concrete)


def _default_bounds(concolic_str: Any, start: Any, end: Any) -> tuple:
    """Fill in None bounds with 0 and string length."""
    if start is None:
        start = concolic_converter.wrap_concolic(0)
    if end is None:
        end = concolic_converter.wrap_concolic(
            len(concolic_converter.unwrap_concolic(concolic_str)),
        )
    return start, end


def _compute_concrete_slice(concolic_str: Any, start: Any, end: Any) -> str:
    """Compute the concrete substring result."""
    return str.__getitem__(
        concolic_str,
        slice(
            concolic_converter.unwrap_concolic(start),
            concolic_converter.unwrap_concolic(end),
        ),
    )


def _is_full_string(start: Any, end: Any, concolic_str: Any) -> bool:
    """Check if the slice covers the entire string (optimization)."""
    return concolic_converter.unwrap_concolic(
        start
    ) == 0 and concolic_converter.unwrap_concolic(end) == len(
        concolic_converter.unwrap_concolic(concolic_str)
    )


def _build_substr_expression(
    concolic_str: Any,
    start: Any,
    end: Any,
    concrete: str,
) -> Any:
    """Build the symbolic str.substr expression."""
    length = concolic_converter.wrap_concolic(
        int(concolic_converter.unwrap_concolic(end))
        - int(concolic_converter.unwrap_concolic(start)),
        ["-", end, start],
        concolic_str.engine,
    )
    return concolic_converter.wrap_concolic(
        concrete,
        ["str.substr", concolic_str, start, length],
        concolic_str.engine,
    )


def _normalize_index(index: Any, concolic_str: Any) -> Any:
    """Normalize negative index to positive, clamping to 0."""
    if concolic_converter.unwrap_concolic(index) >= 0:
        return index

    str_len = concolic_converter.wrap_concolic(
        len(concolic_converter.unwrap_concolic(concolic_str)),
        ["str.len", concolic_str],
        concolic_str.engine,
    )
    normalized = concolic_converter.wrap_concolic(
        concolic_converter.unwrap_concolic(index)
        + concolic_converter.unwrap_concolic(str_len),
        ["+", index, str_len],
        concolic_str.engine,
    )

    if concolic_converter.unwrap_concolic(normalized) < 0:
        return concolic_converter.wrap_concolic(0)

    return normalized


class CaseConverter:
    """Handles case conversion with symbolic tracking."""

    @staticmethod
    def generate_case_expression(
        base_str: Any,
        replacements: list[tuple[str, str]],
    ) -> list:
        """Generate nested str.replaceall expression for case conversion."""
        expr = base_str
        for from_char, to_char in replacements:
            expr = ["str.replace_all", expr, py2smt(from_char), py2smt(to_char)]
        return expr

    @staticmethod
    def to_lower(concolic_str: Any) -> Any:
        """Convert string to lowercase."""
        concrete = str.lower(concolic_str)
        replacements = [(chr(i), chr(i + 32)) for i in range(65, 91)]
        symbolic_expr = CaseConverter.generate_case_expression(
            concolic_str, replacements
        )
        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def to_upper(concolic_str: Any) -> Any:
        """Convert string to uppercase."""
        concrete = str.upper(concolic_str)
        replacements = [(chr(i), chr(i - 32)) for i in range(97, 123)]
        symbolic_expr = CaseConverter.generate_case_expression(
            concolic_str, replacements
        )
        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )


def ensure_concolic_str(value: Any, engine: Any = None) -> Any:
    """Ensure value is a concolic string."""
    from pyct.core import Concolic

    if isinstance(value, Concolic):
        return value

    try:
        str_value = str(value)
    except Exception:
        str_value = ""

    return concolic_converter.wrap_concolic(str_value, None, engine)


def ensure_concolic_int(value: Any, engine: Any = None) -> Any:
    """Ensure value is a concolic int."""
    from pyct.core import Concolic

    if isinstance(value, Concolic):
        if hasattr(value, "to_int"):
            return value.to_int()
        return value

    if isinstance(value, bool):
        value = int(value)

    try:
        int_value = int(value)
    except Exception:
        int_value = 0

    return concolic_converter.wrap_concolic(int_value, None, engine)
