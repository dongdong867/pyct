from __future__ import annotations

import logging
from typing import Any

from pyct.core.str.helpers import (
    SubstringHelper,
    ensure_concolic_int,
    ensure_concolic_str,
)
from pyct.utils import concolic_converter

log = logging.getLogger("ct.con.str.manip")


class StringManipulation:
    """String manipulation operations."""

    @staticmethod
    def replace(concolic_str: Any, old: Any, new: Any, count: int = -1) -> Any:
        """Replace occurrences of substring."""
        concrete = str.replace(
            concolic_str,
            concolic_converter.unwrap_concolic(old),
            concolic_converter.unwrap_concolic(new),
            count,
        )

        old_str = ensure_concolic_str(old, concolic_str.engine)
        new_str = ensure_concolic_str(new, concolic_str.engine)
        count_int = ensure_concolic_int(count, concolic_str.engine)

        if concolic_converter.unwrap_concolic(count_int) < 0:
            return _unbounded_replace(concolic_str, old_str, new_str)

        result = _bounded_replace(concolic_str, old_str, new_str, count_int)
        return _verify_or_fallback(result, concrete, concolic_str.engine)

    @staticmethod
    def split(concolic_str: Any, sep: Any = None, maxsplit: int = -1) -> list:
        """Split string by separator."""
        if sep is None:
            sep = " "

        from pyct.core.str.queries import StringQueries

        sep_idx = StringQueries.find(concolic_str, sep)

        if maxsplit == 0 or concolic_converter.unwrap_concolic(sep_idx) == -1:
            return _split_base_case(concolic_str, sep)

        if maxsplit > 0:
            maxsplit -= 1

        before, after = _split_at_separator(concolic_str, sep, sep_idx)

        if sep is not None or concolic_converter.unwrap_concolic(before):
            return [before] + StringManipulation.split(after, sep, maxsplit)
        return StringManipulation.split(after, sep, maxsplit)

    @staticmethod
    def strip(concolic_str: Any, chars: Any = None) -> Any:
        """Remove leading and trailing characters."""
        from pyct.core.str.transformation import StringTransformation

        concrete = str.strip(concolic_str, concolic_converter.unwrap_concolic(chars))
        result = StringTransformation.lstrip(
            StringTransformation.rstrip(concolic_str, chars),
            chars,
        )
        return _verify_or_fallback(result, concrete, concolic_str.engine)

    @staticmethod
    def splitlines(concolic_str: Any, keepends: bool = False) -> list:
        """Split string at line boundaries."""
        concrete = str.splitlines(
            concolic_str,
            concolic_converter.unwrap_concolic(keepends),
        )

        sep = "\r\n" if "\r\n" in str(concolic_converter.unwrap_concolic(concolic_str)) else "\n"
        result = StringManipulation.split(concolic_str, sep)

        if list(map(concolic_converter.unwrap_concolic, result)) == concrete:
            return result
        return concolic_converter.wrap_concolic(concrete, None, concolic_str.engine)


# ---------------------------------------------------------------------------
# Replace helpers
# ---------------------------------------------------------------------------


def _unbounded_replace(concolic_str: Any, old_str: Any, new_str: Any) -> Any:
    """Replace all occurrences (no count limit)."""
    concrete = str.replace(
        concolic_str,
        concolic_converter.unwrap_concolic(old_str),
        concolic_converter.unwrap_concolic(new_str),
    )
    symbolic_expr = ["str.replace_all", concolic_str, old_str, new_str]
    return concolic_converter.wrap_concolic(concrete, symbolic_expr, concolic_str.engine)


def _bounded_replace(
    concolic_str: Any,
    old_str: Any,
    new_str: Any,
    count_int: Any,
) -> Any:
    """Replace up to *count_int* occurrences iteratively."""
    from pyct.core.str.queries import StringQueries

    old_len = concolic_converter.wrap_concolic(
        len(concolic_converter.unwrap_concolic(old_str)),
        ["str.len", old_str],
        concolic_str.engine,
    )

    result = concolic_converter.wrap_concolic("", None, concolic_str.engine)
    current = concolic_str
    remaining = count_int

    while True:
        if concolic_converter.unwrap_concolic(remaining) == 0:
            return _concat(result, current, concolic_str.engine)

        split_index = StringQueries.find(current, old_str)
        if concolic_converter.unwrap_concolic(split_index) == -1:
            return _concat(result, current, concolic_str.engine)

        before = SubstringHelper.substr(current, None, split_index)
        result = _concat(_concat(result, before, concolic_str.engine), new_str, concolic_str.engine)
        current = SubstringHelper.substr(
            current, _advance_index(split_index, old_len, concolic_str.engine), None
        )
        remaining = _decrement(remaining, concolic_str.engine)


def _advance_index(split_index: Any, old_len: Any, engine: Any) -> Any:
    """Compute the start index after a matched occurrence."""
    return concolic_converter.wrap_concolic(
        concolic_converter.unwrap_concolic(split_index)
        + concolic_converter.unwrap_concolic(old_len),
        ["+", split_index, old_len],
        engine,
    )


def _decrement(value: Any, engine: Any) -> Any:
    """Decrement a concolic integer by 1."""
    return concolic_converter.wrap_concolic(
        concolic_converter.unwrap_concolic(value) - 1,
        ["-", value, "1"],
        engine,
    )


def _concat(left: Any, right: Any, engine: Any) -> Any:
    """Concatenate two concolic strings."""
    concrete = concolic_converter.unwrap_concolic(left) + concolic_converter.unwrap_concolic(right)
    return concolic_converter.wrap_concolic(concrete, ["str.++", left, right], engine)


# ---------------------------------------------------------------------------
# Split helpers
# ---------------------------------------------------------------------------


def _split_base_case(concolic_str: Any, sep: Any) -> list:
    """Handle split base case — no split needed."""
    if sep is not None or concolic_converter.unwrap_concolic(concolic_str):
        return [concolic_str]
    return []


def _split_at_separator(concolic_str: Any, sep: Any, sep_idx: Any) -> tuple:
    """Split string at the separator position, returning (before, after)."""
    before = SubstringHelper.substr(concolic_str, None, sep_idx)
    sep_len = len(concolic_converter.unwrap_concolic(sep))
    after_start = concolic_converter.wrap_concolic(
        concolic_converter.unwrap_concolic(sep_idx) + sep_len,
        ["+", sep_idx, concolic_converter.wrap_concolic(sep_len)],
        concolic_str.engine,
    )
    after = SubstringHelper.substr(concolic_str, after_start, None)
    return before, after


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


def _verify_or_fallback(result: Any, concrete: Any, engine: Any) -> Any:
    """Return result if its concrete value matches, otherwise fall back."""
    if concolic_converter.unwrap_concolic(result) == concrete:
        return result
    return concolic_converter.wrap_concolic(concrete, None, engine)
