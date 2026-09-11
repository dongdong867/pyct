"""Concolic values: real Python values that also carry their symbolic form."""

from __future__ import annotations

import types
from collections.abc import Callable
from types import NotImplementedType

from pyct.core.branch import Branch, BranchSink, Downgrade, Expression, caller_site

# every value-producing int operation pyct has not taught. `__lt__` is taught and stays
# symbolic; `__hash__`, `__repr__` and the pickling hooks are not the target's path and
# stay int's, so a dict key and a debugger read cost nothing.
_UNTAUGHT = (
    "__add__",
    "__radd__",
    "__sub__",
    "__rsub__",
    "__mul__",
    "__rmul__",
    "__truediv__",
    "__rtruediv__",
    "__floordiv__",
    "__rfloordiv__",
    "__mod__",
    "__rmod__",
    "__divmod__",
    "__rdivmod__",
    "__pow__",
    "__rpow__",
    "__lshift__",
    "__rlshift__",
    "__rshift__",
    "__rrshift__",
    "__and__",
    "__rand__",
    "__or__",
    "__ror__",
    "__xor__",
    "__rxor__",
    "__neg__",
    "__pos__",
    "__abs__",
    "__invert__",
    "__index__",
    "__int__",
    "__float__",
    "__round__",
    "__trunc__",
    "__floor__",
    "__ceil__",
    "__bool__",
    "__eq__",
    "__ne__",
    "__gt__",
    "__ge__",
    "__le__",
    "__str__",
    "__format__",
)


class ConcolicBool(int):
    """The result of a symbolic compare. Testing it for truth records the fork.

    It is an int the way `bool` is, because `bool` cannot be subclassed.
    """

    expression: Expression
    sink: BranchSink

    def __new__(cls, value: bool, *, expression: Expression, sink: BranchSink) -> ConcolicBool:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        taken = int.__bool__(self)
        self.sink.append(Branch(expression=self.expression, taken=taken, site=caller_site()))
        return taken

    def __repr__(self) -> str:
        # int.__bool__, not bool(self): bool() would record a fork
        return repr(int.__bool__(self))


class ConcolicInt(int):
    """A real int with a name and a sink.

    Only `<` is symbolic. Any other operation is int's own and returns a
    plain value, with a downgrade in the sink naming what was lost.
    """

    expression: Expression
    sink: BranchSink
    # the loop below installs __eq__ after the class exists, which leaves __hash__ alone.
    # Pinned anyway: it says the hash stays int's, and holds if __eq__ ever moves into the body.
    __hash__ = int.__hash__

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> ConcolicInt:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __lt__(self, other: int) -> ConcolicBool | NotImplementedType:  # type: ignore[override]
        # a bool is an int, but `x < True` is not a compare the solver has a leaf for;
        # a compare's value is a bool the same way
        if not isinstance(other, int) or isinstance(other, bool | ConcolicBool):
            return NotImplemented
        concrete = int.__lt__(self, other)
        return ConcolicBool(
            bool(concrete), expression=["<", self.expression, _form_of(other)], sink=self.sink
        )


def _form_of(value: int) -> Expression:
    """The symbolic form of an operand: its expression if it has one, else itself."""
    return value.expression if isinstance(value, ConcolicInt) else value


def _downgraded(name: str) -> Callable[..., object]:
    """int's own operation, and a note in the sink that the condition was lost.

    The note comes after the call, so an operation that raises records
    nothing and the raise stays the target's. ``NotImplemented`` is not an
    answer either: the other operand's reflected method gets its turn, and
    only a real result is a lost condition.
    """
    operation = getattr(int, name)

    def downgrade(self: ConcolicInt, *args: object) -> object:
        result = operation(self, *args)
        if result is not NotImplemented:
            self.sink.append(Downgrade(name=name))
        return result

    return downgrade


# every closure one `def` makes shares that def's code object, so one of them stands for all
_DOWNGRADE_CODE = _downgraded("__abs__").__code__


def is_downgrade_frame(code: types.CodeType) -> bool:
    """Whether a frame running ``code`` is a downgrade's."""
    return code is _DOWNGRADE_CODE


# forty-odd methods that differ only in the name they call and record, so a loop writes them
for _name in _UNTAUGHT:
    setattr(ConcolicInt, _name, _downgraded(_name))
