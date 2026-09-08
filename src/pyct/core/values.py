"""Concolic values: real Python values that also carry their symbolic form."""

from __future__ import annotations

from pyct.core.branch import Branch, BranchSink, Expression, caller_site


class ConcolicBool:
    """The result of a symbolic compare. Testing it for truth records the fork."""

    def __init__(self, value: bool, *, expression: Expression, sink: BranchSink) -> None:
        self.value = value
        self.expression = expression
        self.sink = sink

    def __bool__(self) -> bool:
        self.sink.append(Branch(expression=self.expression, taken=self.value, site=caller_site()))
        return self.value


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

    def __lt__(self, other: int) -> ConcolicBool:  # type: ignore[override]
        concrete = int.__lt__(self, int(other))
        return ConcolicBool(
            bool(concrete), expression=["<", self.expression, _form_of(other)], sink=self.sink
        )


def _form_of(value: int) -> Expression:
    """The symbolic form of an operand: its expression if it has one, else itself."""
    return value.expression if isinstance(value, ConcolicInt) else value
