"""The concolic float: a real float that also carries its symbolic form.

The `ConcolicFloat` body below is the taught set: the compares, the truth
test, `+ - * /`, the unary operations and `is_integer` stay symbolic, and a
copy is the value itself. `_KEPT` names what is left to float on purpose.
`_INHERITED` names what float inherits rather than defines, which the
derivation at the bottom of the file downgrades along with every other
method float defines. What each operation answers is tracked by the class
numbers holds for its Python type, so this module names no other number's
class (decision numbers-typed-by-python-result).

A float's operations take the float family: a tracked float by its
expression, a plain float as itself. Any other operand gets float's own
answer: NotImplemented where float gives it, as for a str, and a downgrade
named by the dunder where float answers, as for an int or a bool. Never
NotImplemented where float answers: int's own methods answer
NotImplemented for a float, so that would make `f < 3` a TypeError and
`f == 2` False. An int meets a float in follow-floats-that-meet-ints.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core import numbers
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
    """How a float reads the other side of an operation, or None for one it does not take.

    It takes the float family alone. A tracked float reads as its
    expression, and any other float as a literal of its plain value, so a
    float of the target's own prints as a float.
    """
    if isinstance(other, ConcolicFloat):
        return other.expression
    if isinstance(other, float):
        return float.__float__(other)
    return None


def _compare(op: str, name: str) -> Callable[[ConcolicFloat, object], object]:
    """float's own answer to one compare, followed for an operand of the float family.

    Any other operand gets float's own answer and a downgrade named by the
    compare's dunder (see the module docstring).
    """
    followed = numbers.compare(op, getattr(float, name), _operand)
    downgrade = downgraded(float, name)

    def compute(self: ConcolicFloat, other: object) -> object:
        answer = followed(self, other)
        return downgrade(self, other) if answer is NotImplemented else answer

    return compute


def _arithmetic(
    op: str, name: str, *, reflected: bool = False
) -> Callable[[ConcolicFloat, object], object]:
    """float's own answer to one binary operation, carrying the expression that built it.

    The expression keeps Python's written order: a reflected method is
    called on the right operand, so `10.0 - x` is ["-", 10.0, "x"]. A
    division records its zero fork before float's own call, as an int
    division does (``README.md › Rules › division``), so the input that
    raises already lists the fork it died on. Any other operand gets
    float's own answer and a downgrade named by the dunder.
    """
    operation = getattr(float, name)
    downgrade = downgraded(float, name)

    def compute(self: ConcolicFloat, other: object) -> object:
        form = _operand(other)
        if form is None:
            return downgrade(self, other)
        if op == "/":
            numbers.zero_fork(self if reflected else other)
        sides = [form, self.expression] if reflected else [self.expression, form]
        return numbers.tracked(own(operation, self, other), [op, *sides], self.sink)

    return compute


def _itself(self: ConcolicFloat) -> ConcolicFloat:
    """`+x` changes nothing about a float: the value itself, so no node is added."""
    return self


def _is_integer(self: ConcolicFloat, /, *args: object, **kwargs: object) -> Any:
    """float's own `is_integer`, as a tracked bool carrying `["is_integer", x]`.

    The arguments reach float as the target wrote them, so a call with any
    raises float's own TypeError.
    """
    whole = own(float.is_integer, self, *args, **kwargs)
    return numbers.tracked(whole, ["is_integer", self.expression], self.sink)


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
    # float promises a bool from each, and a tracked bool is an int that is not a bool,
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

    # each takes any operand and hands one outside the float family to float, so its signature
    # is not float's; the override breaks float's on purpose
    __add__ = _arithmetic("+", "__add__")  # pyrefly: ignore[bad-override]
    __radd__ = _arithmetic("+", "__radd__", reflected=True)  # pyrefly: ignore[bad-override]
    __sub__ = _arithmetic("-", "__sub__")  # pyrefly: ignore[bad-override]
    __rsub__ = _arithmetic("-", "__rsub__", reflected=True)  # pyrefly: ignore[bad-override]
    __mul__ = _arithmetic("*", "__mul__")  # pyrefly: ignore[bad-override]
    __rmul__ = _arithmetic("*", "__rmul__", reflected=True)  # pyrefly: ignore[bad-override]
    __truediv__ = _arithmetic("/", "__truediv__")  # pyrefly: ignore[bad-override]
    __rtruediv__ = _arithmetic("/", "__rtruediv__", reflected=True)  # pyrefly: ignore[bad-override]
    __neg__ = numbers.unary("-", float.__neg__)
    __abs__ = numbers.unary("abs", float.__abs__)
    __pos__ = _itself
    is_integer = _is_integer

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
# writes them. A float that Python computes, a sum or a quotient among them, is tracked as a
# ConcolicFloat
downgrade_the_rest(ConcolicFloat, float, kept=_KEPT, inherited=_INHERITED)
numbers.enter(float, ConcolicFloat)
