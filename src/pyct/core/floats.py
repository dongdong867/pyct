"""The concolic float: a real float that also carries its symbolic form.

The `ConcolicFloat` body below is the taught set: the compares, the truth
test, `+ - * / // %` and `divmod`, the unary operations, the four roundings
to an int and `is_integer` stay symbolic, `real` and `conjugate` are the
value itself, `fromhex` is float's own, and a copy is the value itself.
`_KEPT` names what is left to float on purpose. `_INHERITED` names what
float inherits rather than defines, which the derivation at the bottom of
the file downgrades along with every other method float defines. What each
operation answers is tracked by the class numbers holds for its Python
type, so this module names no other number's class, and a rounding answers
a tracked int (decision numbers-typed-by-python-result).

A float's operations take a float, an int or a bool, tracked or plain, as
float's own do: a bool is the double 1.0 or 0.0. Those are every operand
float's own operations answer, so any other gets float's NotImplemented, as
a str does, and Python asks the other operand. A float subclass that
defines a reflected operation otherwise than float is asked first, as
Python asks it of a plain float, and a plain answer from it is a downgrade
named by the dunder.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Self

from pyct.core import numbers
from pyct.core.branch import BranchSink, Expression
from pyct.core.values import (
    REPORTED_CLASS,
    as_base,
    built_plainly,
    converted,
    copy_as_itself,
    downgrade_the_rest,
    downgraded,
    forked,
    own,
    pickled,
    refused_delete,
    refused_set,
)

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

# each operation float defines on two operands, and the reflected one Python asks the right
# operand for first when that operand's type is a float subclass defining it otherwise
_REFLECTED = {
    "__add__": "__radd__",
    "__sub__": "__rsub__",
    "__mul__": "__rmul__",
    "__truediv__": "__rtruediv__",
    "__floordiv__": "__rfloordiv__",
    "__mod__": "__rmod__",
    "__divmod__": "__rdivmod__",
    "__pow__": "__rpow__",
    "__lt__": "__gt__",
    "__le__": "__ge__",
    "__gt__": "__lt__",
    "__ge__": "__le__",
    "__eq__": "__eq__",
    "__ne__": "__ne__",
}


def _answered_first(name: str, self: object, other: object, *modulus: object) -> object:
    """What a float subclass on the right answers first, as Python asks it, or NotImplemented.

    With a plain float on the left, Python asks the right operand's
    reflected operation first when its type is a float subclass, a
    library's such as numpy.float64 or the target's own, that defines that
    operation otherwise than float. So pyct asks it too, before anything of
    float's runs, and its answer is the answer, a plain one named as a
    downgrade (see `numbers.reflected_answer`). One that answers
    NotImplemented hands the operation back to float, as it would.
    """
    reflected = _REFLECTED.get(name)
    kind = type(other)
    if reflected is None or kind is float or not issubclass(kind, float):
        return NotImplemented
    operation = getattr(kind, reflected)
    if issubclass(kind, ConcolicFloat) or operation is getattr(float, reflected):
        return NotImplemented
    return numbers.reflected_answer(name, self, other, operation, *modulus)


def _operand(other: object) -> Expression | None:
    """How a float reads the other side of an operation, or None for one it does not take.

    A tracked float reads as its expression, and any other float as a
    literal of its plain value, so a float of the target's own prints as a
    float. An int or a bool reads as the int family reads it
    (`numbers.operand`), and render converts it as Python does.
    """
    if isinstance(other, ConcolicFloat):
        return other.expression
    if isinstance(other, float):
        return float.__float__(other)
    return numbers.operand(other)


type Binary = Callable[[ConcolicFloat, object], object]


def _own(name: str) -> Callable[[object, object], object]:
    """float's own operation by that name, taking an int operand by its plain value.

    See `numbers.plain_int`: a tracked int or bool handed to float's compare
    would record what the target never wrote.
    """
    operation = getattr(float, name)

    def compute(self: object, other: object) -> object:
        return operation(self, numbers.plain_int(other))

    return compute


def _followed(name: str, followed: Callable[..., object]) -> Binary:
    """An operation on two operands, followed for an operand `_operand` takes.

    A float subclass that defines the reflected operation answers first (see
    `_answered_first`). Any other operand is one float's own operation does
    not take either, so its NotImplemented, for a str say, passes through
    with no downgrade.
    """

    def compute(self: ConcolicFloat, other: object) -> object:
        if (first := _answered_first(name, self, other)) is not NotImplemented:
            return first
        return followed(self, other)

    return compute


def _compare(op: str, name: str) -> Binary:
    """float's own answer to one compare, a tracked bool for an operand `_operand` takes."""
    return _followed(name, numbers.compare(op, _own(name), _operand))


def _arithmetic(op: str, name: str, *, reflected: bool = False) -> Binary:
    """float's own answer to one binary operation, carrying the expression that built it.

    The expression keeps Python's written order: a reflected method is
    called on the right operand, so `10.0 - x` is ["-", 10.0, "x"].
    """
    operation = _own(name)
    return _followed(name, numbers.arithmetic(op, operation, _operand, reflected=reflected))


def _division(op: str, name: str, *, reflected: bool = False) -> Binary:
    """float's own division, with the zero fork of a tracked divisor recorded before it.

    `/`, `//` and `%` raise on a zero divisor, -0.0 among them, so each
    records the fork first, as an int division does (``README.md › Rules ›
    division``), and the input that raises lists the fork it died on.
    """
    operation = _own(name)
    return _followed(name, numbers.division(op, operation, _operand, reflected=reflected))


def _divmod(name: str, *, reflected: bool = False) -> Binary:
    """float's own divmod: one zero fork, and the quotient and the remainder, each tracked."""
    return _followed(name, numbers.divmod_of(_own(name), _operand, reflected=reflected))


def _finite(self: ConcolicFloat) -> None:
    """The fork a rounding takes before it runs: NaN and the infinities have no int to round to.

    It is taken true when the float is finite; Python raises ValueError on
    NaN and OverflowError on an infinity, so the input that flips it raises,
    and its line lists the fork it died on.
    """
    forked(self.sink, ["isfinite", self.expression], own(math.isfinite, self), raising=True)


def _rounding(head: str, operation: Callable[[float], int]) -> Callable[[ConcolicFloat], Any]:
    """float's own rounding to an int, a tracked int carrying `[head, x]`, after its finite fork.

    `math.floor`, `math.ceil` and `math.trunc` call it and hand its answer
    back unchanged, as `round` with no digits does.
    """

    def compute(self: ConcolicFloat) -> Any:
        _finite(self)
        return numbers.tracked(own(operation, self), [head, self.expression], self.sink)

    return compute


# `int(x)` on a tracked float, where the code writes it: a tracked int cut toward zero, carrying
# `["int", x]`, after the same finite fork, as `pyct.core.conversions` hands it on
truncated = _rounding("int", float.__int__)


def _round() -> Callable[..., Any]:
    """`round(x)` is a tracked int; `round(x, n)` rounds through a decimal string, a downgrade.

    `round(x, None)` is `round(x)`, as float's own says. Any other form
    reaches float as the target wrote it, so float takes or refuses it.
    """
    whole = _rounding("round", float.__round__)
    to_digits = downgraded(float, "__round__")

    def compute(self: ConcolicFloat, /, *args: object, **kwargs: object) -> Any:
        if not kwargs and (not args or (len(args) == 1 and args[0] is None)):
            return whole(self)
        return to_digits(self, *args, **kwargs)

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
    # the base type, as `isinstance`, singledispatch and a class pattern read it
    __class__ = REPORTED_CLASS  # pyrefly: ignore[bad-override]

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
    __reduce_ex__, __reduce__ = pickled(float)

    # each takes any operand and hands one it does not follow to float, so its signature is not
    # float's; the override breaks float's on purpose
    __add__ = _arithmetic("+", "__add__")  # pyrefly: ignore[bad-override]
    __radd__ = _arithmetic("+", "__radd__", reflected=True)  # pyrefly: ignore[bad-override]
    __sub__ = _arithmetic("-", "__sub__")  # pyrefly: ignore[bad-override]
    __rsub__ = _arithmetic("-", "__rsub__", reflected=True)  # pyrefly: ignore[bad-override]
    __mul__ = _arithmetic("*", "__mul__")  # pyrefly: ignore[bad-override]
    __rmul__ = _arithmetic("*", "__rmul__", reflected=True)  # pyrefly: ignore[bad-override]
    __truediv__ = _division("/", "__truediv__")  # pyrefly: ignore[bad-override]
    __rtruediv__ = _division("/", "__rtruediv__", reflected=True)  # pyrefly: ignore[bad-override]
    __floordiv__ = _division("//", "__floordiv__")  # pyrefly: ignore[bad-override]
    __rfloordiv__ = _division("//", "__rfloordiv__", reflected=True)  # pyrefly: ignore[bad-override]
    __mod__ = _division("%", "__mod__")  # pyrefly: ignore[bad-override]
    __rmod__ = _division("%", "__rmod__", reflected=True)  # pyrefly: ignore[bad-override]
    __divmod__ = _divmod("__divmod__")  # pyrefly: ignore[bad-override]
    __rdivmod__ = _divmod("__rdivmod__", reflected=True)  # pyrefly: ignore[bad-override]
    # each rounding answers a tracked int, the way float's own answers an int
    __floor__ = _rounding("floor", float.__floor__)
    __ceil__ = _rounding("ceil", float.__ceil__)
    __trunc__ = _rounding("trunc", float.__trunc__)
    __round__ = _round()  # pyrefly: ignore[bad-override]
    __neg__ = numbers.unary("-", float.__neg__)
    __abs__ = numbers.unary("abs", float.__abs__)
    __pos__ = _itself
    is_integer = _is_integer
    # float's plain names that hand back the value itself. `imag` stays float's own constant,
    # 0.0, and `as_integer_ratio` and `hex` are derived downgrades
    real = numbers.attribute(float.real, _itself)  # pyrefly: ignore[bad-override]
    conjugate = numbers.itself(float.conjugate, _itself)
    # float's own would build this class from the value alone. Every classmethod float defines
    # is named here, since the derivation reads only methods called on a value
    fromhex = built_plainly(float, "fromhex")  # pyrefly: ignore[bad-override]
    __getformat__ = built_plainly(float, "__getformat__")  # pyrefly: ignore[bad-override]
    if hasattr(float, "from_number"):
        # from 3.14. A tracked float converts to itself, as `float(f)` does
        from_number = converted(float, "from_number")

    # the class called with a value is float's own, a plain float; pyct builds a tracked one
    __new__ = as_base
    # a plain float takes no attribute: a set or a delete is Python's own refusal, pyct's names too
    __setattr__ = refused_set
    __delattr__ = refused_delete

    @classmethod
    def made(cls, value: float, expression: Expression, sink: BranchSink) -> Self:
        """A tracked float of this value and form: how pyct builds one."""
        made = float.__new__(cls, value)
        # the value refuses a set, as a plain one does, so pyct writes its fields straight in
        fields = made.__dict__
        fields["expression"] = expression
        fields["sink"] = sink
        return made

    def __bool__(self) -> bool:
        # zero is the one value on the other side: 0.0 and -0.0 both, and NaN is true
        return forked(self.sink, ["!=", self.expression, 0.0], own(float.__bool__, self))


# the class body above is everything ConcolicFloat teaches. The rest of float, and the
# `__str__` float inherits, differ only in the name they call and record, so the derivation
# writes them. A float that Python computes, a sum or a quotient among them, is tracked as a
# ConcolicFloat
downgrade_the_rest(ConcolicFloat, float, kept=_KEPT, inherited=_INHERITED, first=_answered_first)
numbers.enter(float, ConcolicFloat)
