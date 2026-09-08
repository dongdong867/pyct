"""Concolic values: real Python values that also carry their symbolic form."""

from __future__ import annotations

from types import NotImplementedType

from pyct.core.branch import Branch, BranchSink, Expression, caller_site


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
        return repr(int.__bool__(self))


class ConcolicInt(int):
    """A real int with a name and a sink.

    Only `<` is symbolic. Any other operation is int's own and returns a
    plain int; nothing records the loss.
    """

    expression: Expression
    sink: BranchSink

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> ConcolicInt:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __lt__(self, other: int) -> ConcolicBool | NotImplementedType:  # type: ignore[override]
        # a bool is an int, but `x < True` is not a compare the solver has a leaf for
        if not isinstance(other, int) or isinstance(other, bool):
            return NotImplemented
        concrete = int.__lt__(self, other)
        return ConcolicBool(
            bool(concrete), expression=["<", self.expression, _form_of(other)], sink=self.sink
        )


def _form_of(value: int) -> Expression:
    """The symbolic form of an operand: its expression if it has one, else itself."""
    return value.expression if isinstance(value, ConcolicInt) else value
