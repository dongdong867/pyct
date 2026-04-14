from __future__ import annotations

from typing import Any

from pyct.utils.types import (
    ConcolicEngine,
    ConcolicExpression,
    ConversionResult,
    PrimitiveValue,
    is_concolic_type,
)

# ---------------------------------------------------------------------------
# Lazy-loaded concolic class registry
# ---------------------------------------------------------------------------

_concolic_classes: dict[type, type] | None = None


def _get_concolic_classes() -> dict[type, type]:
    """Lazy-load concolic type → class mapping to avoid circular imports."""
    global _concolic_classes
    if _concolic_classes is None:
        from pyct.core.bool import ConcolicBool
        from pyct.core.float import ConcolicFloat
        from pyct.core.int import ConcolicInt
        from pyct.core.str.str import ConcolicStr

        _concolic_classes = {
            bool: ConcolicBool,
            float: ConcolicFloat,
            int: ConcolicInt,
            str: ConcolicStr,
        }
    return _concolic_classes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_concolic(
    value: Any,
    expr: ConcolicExpression | None = None,
    engine: ConcolicEngine | None = None,
) -> Any:
    """
    Wrap a primitive value in the appropriate concolic object.

    Args:
        value: Primitive value to wrap
        expr: Symbolic expression (optional)
        engine: Concolic execution engine (optional)

    Returns:
        Concolic object, or the original value if not wrappable
    """
    value_type = type(value)
    classes = _get_concolic_classes()

    if value_type in classes:
        return classes[value_type](value, expr, engine)

    if isinstance(value, list):
        return [wrap_concolic(item, expr, engine) for item in value]

    return value


def unwrap_concolic(obj: Any) -> ConversionResult:
    """
    Unwrap a concolic object to its primitive value.

    Args:
        obj: Object to unwrap

    Returns:
        Primitive value, or the original object if not concolic
    """
    if isinstance(obj, list):
        return [unwrap_concolic(item) for item in obj]

    type_name = type(obj).__name__
    if type_name.startswith("Concolic"):
        return _unwrap_concolic(obj, type_name)

    return obj


def convert_to_int(obj: Any) -> int:
    """Convert object to int, handling concolic objects."""
    if is_concolic_type(obj) and hasattr(obj, "__int2__"):
        return obj.__int2__()
    return int(obj)


def convert_to_str(obj: Any) -> str:
    """Convert object to str, handling concolic objects."""
    if is_concolic_type(obj) and hasattr(obj, "__str2__"):
        return obj.__str2__()
    return str(obj)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _unwrap_concolic(obj: Any, type_name: str) -> PrimitiveValue:
    """Unwrap a concolic object using the underlying primitive type methods."""
    unwrap_map = {
        "ConcolicBool": lambda x: bool.__bool__(x),
        "ConcolicFloat": lambda x: float.__float__(x),
        "ConcolicInt": lambda x: int.__int__(x),
        "ConcolicStr": lambda x: str.__str__(x),
    }

    unwrap_func = unwrap_map.get(type_name)
    if unwrap_func:
        return unwrap_func(obj)

    return obj
