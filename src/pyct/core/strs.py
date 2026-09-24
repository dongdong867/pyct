"""The concolic str: a real str that also carries its symbolic form."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.bools import compare
from pyct.core.branch import BranchSink, Expression
from pyct.core.values import downgraded, forked, own

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


def _within_cvc5(other: object) -> bool:
    """Whether the solver reads the other side of a compare as it is.

    A tracked str is read by its expression, and a non-str is Python's own
    business, so only a plain str's characters are checked, each against the
    last one cvc5 holds.
    """
    if isinstance(other, ConcolicStr) or not isinstance(other, str):
        return True
    return all(ord(character) <= LAST_CHARACTER for character in other)


def _compare(op: str, name: str) -> Callable[[ConcolicStr, object], object]:
    """str's own answer to one compare, followed while the solver reads the other side.

    A literal holding a character past the last one cvc5 holds is answered
    by str alone, and the downgrade names the compare's dunder. It is not
    NotImplemented: the literal's reflected compare would answer instead,
    and the line would never say the condition was lost.
    """
    followed = compare(op, getattr(str, name), _operand)
    downgrade = downgraded(str, name)

    def compute(self: ConcolicStr, other: object) -> object:
        return followed(self, other) if _within_cvc5(other) else downgrade(self, other)

    return compute


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
    __lt__ = _compare("<", "__lt__")  # pyrefly: ignore[bad-override]
    __le__ = _compare("<=", "__le__")  # pyrefly: ignore[bad-override]
    __gt__ = _compare(">", "__gt__")  # pyrefly: ignore[bad-override]
    __ge__ = _compare(">=", "__ge__")  # pyrefly: ignore[bad-override]
    __eq__ = _compare("==", "__eq__")  # pyrefly: ignore[bad-override]
    __ne__ = _compare("!=", "__ne__")  # pyrefly: ignore[bad-override]
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
