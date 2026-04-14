from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, Union, runtime_checkable

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from pyct.core.bool import ConcolicBool
    from pyct.core.float import ConcolicFloat
    from pyct.core.int import ConcolicInt
    from pyct.core.str.str import ConcolicStr

# ============================================================================
# Type Aliases
# ============================================================================

ConcolicExpression = Union[list[Any], str, None]
ConcolicEngine = Any  # Forward reference to avoid circular import
PrimitiveValue = Union[bool, int, float, str]
ConversionResult = Union[PrimitiveValue, list["ConversionResult"]]


# ============================================================================
# Protocols
# ============================================================================


@runtime_checkable
class ConcolicProtocol(Protocol):
    """Protocol for objects that support concolic operations."""

    def __int2__(self) -> int:
        """Convert to integer for concolic execution."""
        ...

    def __str2__(self) -> str:
        """Convert to string for concolic execution."""
        ...


@runtime_checkable
class UnwrappableProtocol(Protocol):
    """Protocol for objects that can be unwrapped to primitive values."""

    def __bool__(self) -> bool: ...
    def __int__(self) -> int: ...
    def __float__(self) -> float: ...
    def __str__(self) -> str: ...


# ============================================================================
# Type Aliases for Concolic Objects
# ============================================================================

# Type representing any concolic object
ConcolicType = Union[ConcolicProtocol, Any]

# More specific: A concolic object that wraps a primitive
if TYPE_CHECKING:
    ConcolicWrapper = Union[
        ConcolicBool,
        ConcolicInt,
        ConcolicFloat,
        ConcolicStr,
        ConcolicProtocol,
    ]
else:
    # At runtime, use the protocol
    ConcolicWrapper = Union[ConcolicProtocol, Any]

# ============================================================================
# Enums
# ============================================================================


class SupportedPrimitiveType(Enum):
    """Primitive types supported for concolic execution."""

    BOOL = bool
    INT = int
    FLOAT = float
    STR = str

    @classmethod
    def is_supported(cls, value_type: type) -> bool:
        """Check if a type is supported."""
        return value_type in (member.value for member in cls)


# ============================================================================
# Helper Functions
# ============================================================================


def is_concolic_type(obj: Any) -> bool:
    """
    Check if object is a concolic type.

    Args:
        obj: Object to check

    Returns:
        True if object is a concolic type
    """
    return type(obj).__name__.startswith("Concolic")
