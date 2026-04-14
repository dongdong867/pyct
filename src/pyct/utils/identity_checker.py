from __future__ import annotations

from typing import Any

from pyct.utils.concolic_converter import unwrap_concolic
from pyct.utils.types import is_concolic_type


def is_identical(obj1: Any, obj2: Any) -> bool:
    """
    Check if two objects are identical, handling concolic types.

    Handles concolic objects by unwrapping them before comparison.

    Args:
        obj1: First object
        obj2: Second object

    Returns:
        True if objects are identical
    """
    if obj1 is obj2:
        return True

    unwrapped1 = unwrap_concolic(obj1) if is_concolic_type(obj1) else obj1
    unwrapped2 = unwrap_concolic(obj2) if is_concolic_type(obj2) else obj2

    return unwrapped1 is unwrapped2
