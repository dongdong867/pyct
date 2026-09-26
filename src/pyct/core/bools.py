"""The concolic bool: what every concolic type answers a compare with.

`compare` lives here rather than in values. It builds a ConcolicBool, and
ConcolicBool needs values' helpers, so a compare in values would make
values and bools import each other.

A tracked bool is also a number, the int 1 or 0, as Python's bool is, so
its arithmetic and its compares are ConcolicInt's own, run on it. ints
imports this module for `compare`, so ConcolicInt is read when such an
operation runs, not when the class is built.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, Protocol

from pyct.core.branch import BranchSink, Expression
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own

# what a tracked int, and a tracked bool with it, leaves to int on purpose. A bool is the int 1
# or 0, so both keep the same names; they sit here, below ints, so both derivations read one
# copy. The derivations downgrade every other method int defines.

# not the target's path: `__hash__`, `__repr__`, the pickling hook and the rest of the object
# plumbing, so a dict key and a debugger read cost nothing. `__getattribute__` is kept for a
# harder reason: the downgrade wrapper reads `self.sink`, which goes through `__getattribute__`
# itself, so a wrapped one recurses on the first attribute read
INT_KEPT = (
    "__hash__",
    "__repr__",
    "__getnewargs__",
    "__new__",
    "__getattribute__",
    "__sizeof__",
)

# int's plain methods record nothing yet. The ticket that wraps them is
# `report-a-plain-int-method-as-a-downgrade`; until it lands, these stay int's own
INT_NOT_YET = (
    "as_integer_ratio",
    "bit_count",
    "bit_length",
    "conjugate",
    "is_integer",
    "to_bytes",
)

# int inherits `__str__` from object, so reading what int itself defines never reaches it, and
# `print(x)` still drops the condition
INT_INHERITED = ("__str__",)


def _ints() -> ModuleType:
    """The ints module, read when an operation runs: ints imports this one, for `compare`."""
    from pyct.core import ints

    return ints


def _as_an_int(name: str) -> Callable[..., Any]:
    """ConcolicInt's taught operation `name`, run on the bool as the int 1 or 0 it is.

    The operation reads only the bool's expression and sink, so the node it
    builds holds the bool's condition, and a division by the bool forks on
    that condition, as `if` would test it.
    """

    def compute(self: ConcolicBool, /, *args: object) -> Any:
        return getattr(_ints().ConcolicInt, name)(self, *args)

    return compute


def _the_int(self: ConcolicBool) -> Any:
    """The int a bool is, 1 or 0, with the same condition: `+True` is 1, and adds no node."""
    return _ints().ConcolicInt(own(int.__index__, self), expression=self.expression, sink=self.sink)


def _rounded(self: ConcolicBool, ndigits: object = None) -> object:
    """Rounding a bool rounds the int it is: 1 or 0 to any digits, a downgrade to tens."""
    return _the_int(self).__round__(ndigits)


def _logical(op: str, name: str) -> Callable[[ConcolicBool, object], object]:
    """Python's `&`, `|` or `^` between two bools: a bool, on the conditions of both.

    A plain True or False is a literal, a tracked bool its condition. With
    an int on the other side it is int's bitwise operation, which stays a
    downgrade (follow-integers).
    """
    operation = getattr(int, name)
    downgrade = downgraded(int, name)

    def compute(self: ConcolicBool, other: object) -> object:
        if not isinstance(other, bool | ConcolicBool):
            return downgrade(self, other)
        form = other.expression if isinstance(other, ConcolicBool) else other
        return ConcolicBool(
            bool(own(operation, self, other)),
            expression=[op, self.expression, form],
            sink=self.sink,
        )

    return compute


def _formatted(self: ConcolicBool, spec: str) -> str:
    """How Python formats the bool this is: `True` with no spec, as the int 1 with one."""
    # int.__bool__, not bool(self): bool() would record a fork
    return format(int.__bool__(self), spec)


class ConcolicBool(int):
    """The result of a symbolic compare. Testing it for truth records the fork.

    It is an int the way `bool` is, because `bool` cannot be subclassed. The
    operations taught below stay symbolic. Any other operation is int's own
    and returns a plain value, with a downgrade in the sink naming what was
    lost.
    """

    expression: Expression
    sink: BranchSink

    # a compare or an arithmetic operation reads the bool as the int 1 or 0. int promises a
    # bool from a compare, and a ConcolicBool is an int that is not a bool; the override
    # breaks that promise on purpose, as ConcolicInt's does
    __lt__ = _as_an_int("__lt__")
    __le__ = _as_an_int("__le__")
    __gt__ = _as_an_int("__gt__")
    __ge__ = _as_an_int("__ge__")
    __eq__ = _as_an_int("__eq__")
    __ne__ = _as_an_int("__ne__")
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

    __add__ = _as_an_int("__add__")
    __radd__ = _as_an_int("__radd__")
    __sub__ = _as_an_int("__sub__")
    __rsub__ = _as_an_int("__rsub__")
    __mul__ = _as_an_int("__mul__")
    __rmul__ = _as_an_int("__rmul__")
    __floordiv__ = _as_an_int("__floordiv__")
    __rfloordiv__ = _as_an_int("__rfloordiv__")
    __mod__ = _as_an_int("__mod__")
    __rmod__ = _as_an_int("__rmod__")
    __divmod__ = _as_an_int("__divmod__")
    __rdivmod__ = _as_an_int("__rdivmod__")
    __neg__ = _as_an_int("__neg__")
    __abs__ = _as_an_int("__abs__")
    __pow__ = _as_an_int("__pow__")
    __pos__ = _the_int
    __index__ = _the_int
    __trunc__ = _the_int
    __floor__ = _the_int
    __ceil__ = _the_int
    __round__ = _rounded  # pyrefly: ignore[bad-override]

    # `&`, `|` and `^` between two bools answer a bool; with an int, a downgrade
    __and__ = _logical("&", "__and__")  # pyrefly: ignore[bad-override]
    __or__ = _logical("|", "__or__")  # pyrefly: ignore[bad-override]
    __xor__ = _logical("^", "__xor__")  # pyrefly: ignore[bad-override]

    # the text drops the condition, so it stays a downgrade, but it is the bool's text. An
    # f-string records this one entry: int's own would read `__str__` first
    __format__ = downgraded(int, "__format__", calling=_formatted)  # pyrefly: ignore[bad-override]

    def __new__(cls, value: bool, *, expression: Expression, sink: BranchSink) -> ConcolicBool:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        return forked(self.sink, self.expression, own(int.__bool__, self))

    def __repr__(self) -> str:
        # int.__bool__, not bool(self): bool() would record a fork
        return repr(int.__bool__(self))


class _Symbolic(Protocol):
    """A value with a symbolic form and a sink: all a compare needs of the type it is set on."""

    expression: Expression
    sink: BranchSink


def compare(
    op: str, operation: Callable[..., bool], operand: Callable[[object], Expression | None]
) -> Callable[[_Symbolic, object], ConcolicBool]:
    """The base type's own answer to one comparison, carrying the condition that produced it.

    `operand` is the concolic type's rule for the other side: the symbolic
    form of an operand the type takes, or None for one it does not. None
    answers NotImplemented, so the other operand gets its turn.

    Now that `==` answers with a ConcolicBool, `x in [1, 2, 3]` and a dict
    lookup on a key that is equal without being the same one test that answer
    for truth, so each records a fork at the target's line.
    """

    def compute(self: _Symbolic, other: object) -> ConcolicBool:
        form = operand(other)
        if form is None:
            return NotImplemented
        return ConcolicBool(
            bool(own(operation, self, other)),
            expression=[op, self.expression, form],
            sink=self.sink,
        )

    return compute


# the class body above is everything ConcolicBool teaches. The rest of int, and the `__str__`
# int inherits, differ only in the name they call and record, so the derivation writes them
downgrade_the_rest(ConcolicBool, int, kept=INT_KEPT + INT_NOT_YET, inherited=INT_INHERITED)
