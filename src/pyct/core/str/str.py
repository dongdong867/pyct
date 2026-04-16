# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import logging
from typing import Any

from pyct.core import Concolic, MetaFinal
from pyct.core.str.character_checks import CharacterChecks
from pyct.core.str.helpers import SubstringHelper
from pyct.core.str.manipulation import StringManipulation
from pyct.core.str.operations import StringBinaryOperations
from pyct.core.str.queries import StringQueries
from pyct.core.str.transformation import StringTransformation
from pyct.utils import concolic_converter
from pyct.utils.smt_converter import py2smt
from pyct.utils.types import ConcolicType

log = logging.getLogger("ct.con.str")


class ConcolicStr(str, Concolic, metaclass=MetaFinal):
    """
    A string value that tracks both concrete and symbolic representations.

    ConcolicStr supports string operations with symbolic execution capabilities,
    enabling automated test generation through constraint solving.

    Examples:
        >>> cs = ConcolicStr("hello", "x", engine)
        >>> result = cs + " world"
        >>> result.expr
        ["str.++", cs, " world"]

        >>> cs.startswith("hel")
        ConcolicBool(True, ["str.prefixof", "hel", cs])
    """

    def __new__(
        cls,
        value: Any,
        expr: Any | None = None,
        engine: Any | None = None,
    ) -> ConcolicStr:
        """Create a new ConcolicStr instance."""
        if not isinstance(value, str):
            try:
                value = str(value)
            except Exception as e:
                raise TypeError(f"Cannot convert {type(value).__name__} to str: {e}") from e

        instance = str.__new__(cls, value)
        return instance

    def __init__(
        self,
        value: Any,
        expr: Any | None = None,
        engine: Any | None = None,
    ) -> None:
        """Initialize concolic attributes."""
        super().__init__(expr=expr, engine=engine)

        if log.isEnabledFor(logging.DEBUG):
            log.debug("ConcolicStr created: value=%s, expr=%s", str(self), self.expr)

    # ========================================================================
    # Binary Operations
    # ========================================================================

    def __add__(self, other: Any) -> ConcolicType:
        """String concatenation: self + other."""
        return StringBinaryOperations(self).add(other)

    def __radd__(self, other: Any) -> ConcolicType:
        """Reverse string concatenation: other + self."""
        return StringBinaryOperations(self).radd(other)

    def __mul__(self, other: Any) -> ConcolicType:
        """String repetition: self * n."""
        return StringBinaryOperations(self).mul(other)

    def __rmul__(self, other: Any) -> ConcolicType:
        """Reverse string repetition: n * self."""
        return StringBinaryOperations(self).mul(other)

    def __contains__(self, other: Any) -> ConcolicType:
        """Containment check: other in self."""
        return StringBinaryOperations(self).contains(other)

    def __eq__(self, other: Any) -> ConcolicType:
        """Equality: self == other."""
        return StringBinaryOperations(self).eq(other)

    def __ne__(self, other: Any) -> ConcolicType:
        """Inequality: self != other."""
        return StringBinaryOperations(self).ne(other)

    def __lt__(self, other: Any) -> ConcolicType:
        """Less than: self < other."""
        return StringBinaryOperations(self).lt(other)

    def __le__(self, other: Any) -> ConcolicType:
        """Less than or equal: self <= other."""
        return StringBinaryOperations(self).le(other)

    def __gt__(self, other: Any) -> ConcolicType:
        """Greater than: self > other."""
        return StringBinaryOperations(self).gt(other)

    def __ge__(self, other: Any) -> ConcolicType:
        """Greater than or equal: self >= other."""
        return StringBinaryOperations(self).ge(other)

    # ========================================================================
    # String Access and Length
    # ========================================================================

    def __len__(self) -> ConcolicType:
        """Return length of string."""
        concrete = str.__len__(self)
        symbolic_expr = ["str.len", self]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __getitem__(self, key: Any) -> ConcolicType:
        """Get character or substring by index/slice."""
        if isinstance(key, int):
            return self._getitem_int(key)

        if isinstance(key, slice):
            if key.step is not None and key.step != 1:
                # Step slices (e.g. [::-1]) can't be represented in SMT-LIB.
                # Compute correct concrete result, drop symbolic tracking.
                concrete = str.__getitem__(self, key)
                return concolic_converter.wrap_concolic(concrete, None, self.engine)
            return SubstringHelper.substr(self, key.start, key.stop)

        return concolic_converter.wrap_concolic(
            str.__getitem__(self, concolic_converter.unwrap_concolic(key)),
            None,
            self.engine,
        )

    def _getitem_int(self, key: Any) -> ConcolicType:
        """Handle single character access by integer index."""
        (self.__len__() > key).__bool__()

        concrete = str.__getitem__(self, concolic_converter.unwrap_concolic(key))

        from pyct.core.str.helpers import ensure_concolic_int

        key_concolic = ensure_concolic_int(key, self.engine)
        key_concolic = _normalize_negative_index(key_concolic, key, self)

        symbolic_expr = ["str.at", self, key_concolic]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def __iter__(self):
        """Iterate over characters in string."""
        index = concolic_converter.wrap_concolic(0, None, self.engine)
        # IMPORTANT: Don't unwrap for comparison! The comparison must be symbolic
        # to generate path constraints even for empty strings.
        # Legacy behavior: `while (index < self.__len__()):`
        while index < self.__len__():
            yield self.__getitem__(index)
            index = concolic_converter.wrap_concolic(
                concolic_converter.unwrap_concolic(index) + 1,
                ["+", index, "1"],
                self.engine,
            )

    def __bool__(self) -> bool:
        """Convert to boolean (non-empty check)."""
        concrete = bool(concolic_converter.unwrap_concolic(self))
        symbolic_expr = ["not", ["=", self, py2smt("")]]

        # Insert branch for symbolic execution
        concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine).__bool__()

        return concrete

    def __int__(self) -> int:
        """
        Convert string to integer (for int() built-in).

        This allows code like `int(concolic_str)` to work properly during
        concolic execution. When int() succeeds, PyCT will track this as
        a constraint on the string content.

        Raises:
            ValueError: If the string cannot be converted to an integer
        """
        # Try to convert the concrete value
        try:
            concrete_value = int(str.__str__(self))
        except (ValueError, TypeError) as e:
            # Conversion failed - this creates a path constraint
            # PyCT will try to avoid inputs that lead here
            raise ValueError(f"invalid literal for int() with base 10: '{self}'") from e

        # Successful conversion - return concrete int
        # The constraint that this path was taken is tracked by PyCT
        return concrete_value

    def __hash__(self) -> int:
        """Return hash (must return primitive)."""
        return str.__hash__(self)

    # ========================================================================
    # String Query Methods
    # ========================================================================

    def find(self, *args) -> ConcolicType:
        """Find substring, return index or -1."""
        return StringQueries.find(self, *args)

    def index(self, *args) -> ConcolicType:
        """Find substring, return index or raise ValueError."""
        return StringQueries.index(self, *args)

    def count(self, *args) -> ConcolicType:
        """Count non-overlapping occurrences."""
        return StringQueries.count(self, *args)

    def startswith(self, *args) -> ConcolicType:
        """Check if string starts with prefix."""
        return StringQueries.startswith(self, *args)

    def endswith(self, *args) -> ConcolicType:
        """Check if string ends with suffix."""
        return StringQueries.endswith(self, *args)

    # ========================================================================
    # String Manipulation Methods
    # ========================================================================

    def replace(self, old: Any, new: Any, count: int = -1) -> ConcolicType:
        """Replace occurrences of substring."""
        return StringManipulation.replace(self, old, new, count)

    def split(self, sep: Any = None, maxsplit: int = -1) -> list:
        """Split string by separator."""
        return StringManipulation.split(self, sep, maxsplit)

    def strip(self, chars: Any = None) -> ConcolicType:
        """Remove leading and trailing characters."""
        return StringManipulation.strip(self, chars)

    def lstrip(self, chars: Any = None) -> ConcolicType:
        """Remove leading characters."""
        return StringTransformation.lstrip(self, chars)

    def rstrip(self, chars: Any = None) -> ConcolicType:
        """Remove trailing characters."""
        return StringTransformation.rstrip(self, chars)

    def splitlines(self, keepends: bool = False) -> list:
        """Split at line boundaries."""
        return StringManipulation.splitlines(self, keepends)

    # ========================================================================
    # String Transformation Methods
    # ========================================================================

    def lower(self) -> ConcolicType:
        """Convert to lowercase."""
        return StringTransformation.lower(self)

    def upper(self) -> ConcolicType:
        """Convert to uppercase."""
        return StringTransformation.upper(self)

    # ========================================================================
    # Character Classification Methods
    # ========================================================================

    def isalpha(self) -> ConcolicType:
        """Check if string is alphabetic."""
        return CharacterChecks.isalpha(self)

    def isalnum(self) -> ConcolicType:
        """Check if string is alphanumeric."""
        return CharacterChecks.isalnum(self)

    def isdigit(self) -> ConcolicType:
        """Check if string is all digits."""
        return CharacterChecks.isdigit(self)

    def isnumeric(self) -> ConcolicType:
        """Check if string is numeric."""
        return CharacterChecks.isnumeric(self)

    def islower(self) -> ConcolicType:
        """Check if string is lowercase."""
        return CharacterChecks.islower(self)

    def isupper(self) -> ConcolicType:
        """Check if string is uppercase."""
        return CharacterChecks.isupper(self)

    # ========================================================================
    # Type Conversions
    # ========================================================================

    def to_bool(self) -> ConcolicType:
        """Convert to ConcolicBool (non-empty check)."""
        concrete = bool(concolic_converter.unwrap_concolic(self))
        symbolic_expr = ["not", ["=", self, py2smt("")]]
        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def to_int(self) -> ConcolicType:
        """Convert string to ConcolicInt."""
        # Check if valid integer
        CharacterChecks.is_integer_string(self).__bool__()

        concrete = int(self)

        # Handle negative numbers
        symbolic_expr = [
            "ite",
            ["str.prefixof", py2smt("-"), self],
            ["-", ["str.to_int", ["str.substr", self, "1", ["str.len", self]]]],
            ["str.to_int", self],
        ]

        return concolic_converter.wrap_concolic(concrete, symbolic_expr, self.engine)

    def to_str(self) -> ConcolicStr:
        """Convert to ConcolicStr (identity)."""
        return self

    # ========================================================================
    # Methods Returning Concrete Values (TODO: Add symbolic tracking)
    # ========================================================================

    def capitalize(self) -> ConcolicType:
        """Capitalize first character."""
        return concolic_converter.wrap_concolic(str.capitalize(self), None, self.engine)

    def casefold(self) -> ConcolicType:
        """Return casefolded string."""
        return concolic_converter.wrap_concolic(str.casefold(self), None, self.engine)

    def center(self, width: Any, fillchar: str = " ") -> ConcolicType:
        """Center string in field of given width."""
        return concolic_converter.wrap_concolic(
            str.center(
                self,
                concolic_converter.unwrap_concolic(width),
                concolic_converter.unwrap_concolic(fillchar),
            ),
            None,
            self.engine,
        )

    def encode(self, encoding: str = "utf-8", errors: str = "strict") -> ConcolicType:
        """Encode string to bytes."""
        return concolic_converter.wrap_concolic(
            str.encode(
                self,
                concolic_converter.unwrap_concolic(encoding),
                concolic_converter.unwrap_concolic(errors),
            ),
            None,
            self.engine,
        )

    def expandtabs(self, tabsize: int = 8) -> ConcolicType:
        """Expand tabs to spaces."""
        return concolic_converter.wrap_concolic(
            str.expandtabs(self, concolic_converter.unwrap_concolic(tabsize)),
            None,
            self.engine,
        )

    def format(self, *args, **kwargs) -> ConcolicType:
        """Format string."""
        args = tuple(concolic_converter.unwrap_concolic(arg) for arg in args)
        kwargs = {k: concolic_converter.unwrap_concolic(v) for k, v in kwargs.items()}
        return concolic_converter.wrap_concolic(
            str.format(self, *args, **kwargs), None, self.engine
        )

    def join(self, iterable) -> ConcolicType:
        """Join iterable of strings."""
        return concolic_converter.wrap_concolic(
            str.join(self, concolic_converter.unwrap_concolic(iterable)),
            None,
            self.engine,
        )

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return f"ConcolicStr({concolic_converter.unwrap_concolic(self)!r})"


def _normalize_negative_index(key_concolic: Any, key: Any, concolic_str: Any) -> Any:
    """Normalize a negative index to a positive one, clamping to 0."""
    if concolic_converter.unwrap_concolic(key) >= 0:
        return key_concolic

    key_concolic = concolic_converter.wrap_concolic(
        concolic_converter.unwrap_concolic(key_concolic)
        + len(concolic_converter.unwrap_concolic(concolic_str)),
        ["+", key_concolic, ["str.len", concolic_str]],
        concolic_str.engine,
    )
    if concolic_converter.unwrap_concolic(key_concolic) < 0:
        return concolic_converter.wrap_concolic(0)

    return key_concolic
