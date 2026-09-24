"""The concolic str: a real str that also carries its symbolic form."""

from __future__ import annotations

from pyct.core.bools import compare
from pyct.core.branch import BranchSink, Expression
from pyct.core.values import forked, own

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

    # Python swaps the operands of a reflected compare itself, so `"b" < s` runs
    # `s.__gt__("b")` and prints [">", "s", "'b'"]; nothing here has to reflect anything.
    # str promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    __lt__ = compare("<", str.__lt__, _operand)  # pyrefly: ignore[bad-override]
    __le__ = compare("<=", str.__le__, _operand)  # pyrefly: ignore[bad-override]
    __gt__ = compare(">", str.__gt__, _operand)  # pyrefly: ignore[bad-override]
    __ge__ = compare(">=", str.__ge__, _operand)  # pyrefly: ignore[bad-override]
    __eq__ = compare("==", str.__eq__, _operand)  # pyrefly: ignore[bad-override]
    __ne__ = compare("!=", str.__ne__, _operand)  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = str.__hash__

    def __new__(cls, value: str, *, expression: Expression, sink: BranchSink) -> ConcolicStr:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # str has no __bool__ and Python falls to __len__; this one comes first. The empty
        # string is the one value that takes the other side, written as repr writes it
        return forked(self.sink, ["!=", self.expression, "''"], own(str.__len__, self) > 0)
