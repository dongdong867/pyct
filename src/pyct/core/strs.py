"""The concolic str: a real str that also carries its symbolic form."""

from __future__ import annotations

from pyct.core.bools import compare
from pyct.core.branch import BranchSink, Expression

# the last character cvc5 holds: its strings run from U+0000 to here, and the solver writes
# every one of them
LAST_CHARACTER = 0x2FFFF


def _operand(other: object) -> Expression | None:
    """The symbolic form of an operand str takes, or None for one it does not.

    A tracked str gives its expression. Any other str is a literal of its
    plain value, written as repr writes it, so a literal keeps its quotes and
    reads apart from a parameter name.
    """
    if isinstance(other, ConcolicStr):
        return other.expression
    if isinstance(other, str):
        # str's own repr: a str of the target's own may print itself another way
        return str.__repr__(other)
    return None


class ConcolicStr(str):
    """A real str with a name and a sink.

    The operations taught below stay symbolic.
    """

    expression: Expression
    sink: BranchSink

    # str promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    __eq__ = compare("==", str.__eq__, _operand)  # pyrefly: ignore[bad-override]
    __ne__ = compare("!=", str.__ne__, _operand)  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = str.__hash__

    def __new__(cls, value: str, *, expression: Expression, sink: BranchSink) -> ConcolicStr:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self
