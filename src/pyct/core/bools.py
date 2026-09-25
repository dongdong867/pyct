"""The concolic bool: what every concolic type answers a compare with.

`compare` lives here rather than in values. It builds a ConcolicBool, and
ConcolicBool needs values' helpers, so a compare in values would make
values and bools import each other.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pyct.core.branch import BranchSink, Expression
from pyct.core.values import copy_as_itself, forked, own


class ConcolicBool(int):
    """The result of a symbolic compare. Testing it for truth records the fork.

    It is an int the way `bool` is, because `bool` cannot be subclassed.
    """

    expression: Expression
    sink: BranchSink

    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

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
