"""The concolic float: a real float that also carries its symbolic form.

The `ConcolicFloat` body below is the taught set: the compares, the truth
test, `+ - * /`, the unary operations and `is_integer` stay symbolic, and a
copy is the value itself. `_KEPT` names what is left to float on purpose.
`_INHERITED` names what float inherits rather than defines, which the
derivation at the bottom of the file downgrades along with every other
method float defines.

An operand pyct does not encode, an int or a bool, is float's own answer and
a downgrade named by the dunder, never NotImplemented as it is for
`ConcolicInt`. int's own methods answer NotImplemented for a float, so a
NotImplemented here would make `f < 3` a TypeError and `f == 2` False. Where
float itself answers NotImplemented, for a str, the downgrade records nothing
and Python goes on as it does for a plain float.
"""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.bools import ConcolicBool, compare
from pyct.core.branch import BranchSink, Expression
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own

# not the target's path: `__hash__`, `__repr__`, the pickling hook and the rest of the object
# plumbing, so a dict key and a debugger read cost nothing. `__getattribute__` is kept for a
# harder reason: the downgrade wrapper reads `self.sink`, which goes through `__getattribute__`
# itself, so a wrapped one recurses on the first attribute read
_KEPT = (
    "__hash__",
    "__repr__",
    "__getnewargs__",
    "__new__",
    "__getattribute__",
    "__sizeof__",
)

# float inherits `__str__` from object, so reading what float itself defines never reaches it,
# and `print(x)` still drops the condition
_INHERITED = ("__str__",)


def _operand(other: object) -> Expression | None:
    """The symbolic form of an operand pyct encodes beside a float, or None for any other.

    A tracked float gives its expression, and any other float is a literal
    of its plain value, so a float of the target's own prints as a float.
    """
    if isinstance(other, ConcolicFloat):
        return other.expression
    if isinstance(other, float):
        return float.__float__(other)
    return None


def _compare(op: str, name: str) -> Callable[[ConcolicFloat, object], object]:
    """float's own answer to one compare, followed for an operand pyct encodes.

    Any other operand is float's own answer and a downgrade named by the
    compare's dunder (see the module docstring).
    """
    followed = compare(op, getattr(float, name), _operand)
    downgrade = downgraded(float, name)

    def compute(self: ConcolicFloat, other: object) -> object:
        answer = followed(self, other)
        return downgrade(self, other) if answer is NotImplemented else answer

    return compute


def _zero_fork(divisor: object) -> None:
    """The fork a tracked divisor takes on its way into a division: `["!=", divisor, 0.0]`.

    Testing it for truth is what records it, so `ConcolicFloat.__bool__` and
    `forked` stay the one place a fork is written. A plain divisor has
    nothing to flip and records nothing.
    """
    if isinstance(divisor, ConcolicFloat):
        bool(divisor)


def _arithmetic(
    op: str, name: str, *, reflected: bool = False
) -> Callable[[ConcolicFloat, object], object]:
    """float's own answer to one binary operation, carrying the expression that built it.

    The expression keeps Python's written order: a reflected method is
    called on the right operand, so `10.0 - x` is ["-", 10.0, "x"]. A
    division records its zero fork before float's own call, as an int
    division does (``README.md › Rules › division``), so the input that
    raises already lists the fork it died on. Any other operand is float's
    own answer and a downgrade named by the dunder.
    """
    operation = getattr(float, name)
    downgrade = downgraded(float, name)

    def compute(self: ConcolicFloat, other: object) -> object:
        form = _operand(other)
        if form is None:
            return downgrade(self, other)
        if op == "/":
            _zero_fork(self if reflected else other)
        operands = [form, self.expression] if reflected else [self.expression, form]
        return ConcolicFloat(
            own(operation, self, other), expression=[op, *operands], sink=self.sink
        )

    return compute


def _unary(
    op: str, operation: Callable[[float], float]
) -> Callable[[ConcolicFloat], ConcolicFloat]:
    """float's own answer to one unary operation, under the head the builtin or operator has."""

    def compute(self: ConcolicFloat) -> ConcolicFloat:
        return ConcolicFloat(own(operation, self), expression=[op, self.expression], sink=self.sink)

    return compute


def _itself(self: ConcolicFloat) -> ConcolicFloat:
    """`+x` changes nothing about a float: the value itself, so no node is added."""
    return self


def _is_integer(self: ConcolicFloat, /, *args: object, **kwargs: object) -> ConcolicBool:
    """float's own `is_integer`, as a tracked bool carrying `["is_integer", x]`.

    The arguments reach float as the target wrote them, so a call with any
    raises float's own TypeError.
    """
    whole = own(float.is_integer, self, *args, **kwargs)
    return ConcolicBool(whole, expression=["is_integer", self.expression], sink=self.sink)


class ConcolicFloat(float):
    """A real float with a name and a sink.

    The operations taught below stay symbolic. Any other method float defines,
    except those left to it in `_KEPT`, is float's own and returns a plain value,
    with a downgrade in the sink naming what was lost: a method by its name, an
    operator by its dunder (``README.md › Rules › downgrades``).
    """

    expression: Expression
    sink: BranchSink

    # Python swaps the operands of a reflected compare itself, so `2.5 < x` runs
    # `x.__gt__(2.5)` and prints [">", "x", 2.5]; nothing here has to reflect anything.
    # float promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose
    __lt__ = _compare("<", "__lt__")  # pyrefly: ignore[bad-override]
    __le__ = _compare("<=", "__le__")  # pyrefly: ignore[bad-override]
    __gt__ = _compare(">", "__gt__")  # pyrefly: ignore[bad-override]
    __ge__ = _compare(">=", "__ge__")  # pyrefly: ignore[bad-override]
    __eq__ = _compare("==", "__eq__")  # pyrefly: ignore[bad-override]
    __ne__ = _compare("!=", "__ne__")  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = float.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

    # each takes any operand and hands one pyct does not encode to float, so its signature is
    # not float's; the override breaks float's on purpose
    __add__ = _arithmetic("+", "__add__")  # pyrefly: ignore[bad-override]
    __radd__ = _arithmetic("+", "__radd__", reflected=True)  # pyrefly: ignore[bad-override]
    __sub__ = _arithmetic("-", "__sub__")  # pyrefly: ignore[bad-override]
    __rsub__ = _arithmetic("-", "__rsub__", reflected=True)  # pyrefly: ignore[bad-override]
    __mul__ = _arithmetic("*", "__mul__")  # pyrefly: ignore[bad-override]
    __rmul__ = _arithmetic("*", "__rmul__", reflected=True)  # pyrefly: ignore[bad-override]
    __truediv__ = _arithmetic("/", "__truediv__")  # pyrefly: ignore[bad-override]
    __rtruediv__ = _arithmetic("/", "__rtruediv__", reflected=True)  # pyrefly: ignore[bad-override]
    __neg__ = _unary("-", float.__neg__)
    __abs__ = _unary("abs", float.__abs__)
    __pos__ = _itself
    # float promises a bool, and a ConcolicBool is an int that is not a bool
    is_integer = _is_integer  # pyrefly: ignore[bad-override]

    def __new__(cls, value: float, *, expression: Expression, sink: BranchSink) -> ConcolicFloat:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # zero is the one value on the other side: 0.0 and -0.0 both, and NaN is true
        return forked(self.sink, ["!=", self.expression, 0.0], own(float.__bool__, self))


# the class body above is everything ConcolicFloat teaches. The rest of float, and the
# `__str__` float inherits, differ only in the name they call and record, so the derivation
# writes them
downgrade_the_rest(ConcolicFloat, float, kept=_KEPT, inherited=_INHERITED)
