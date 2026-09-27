"""The concolic int: a real int that also carries its symbolic form."""

from __future__ import annotations

from pyct.core import numbers, texts
from pyct.core.branch import BranchSink, Expression
from pyct.core.numbers import (
    INT_KEPT,
    answered_first,
    asked_first,
    compare,
    promoted,
)
from pyct.core.values import (
    built_plainly,
    copy_as_itself,
    downgrade_the_rest,
    downgraded,
    forked,
    own,
    pickled,
)

# the `ConcolicInt` body below is the taught set: the comparisons, the truth test, the
# arithmetic, the division and the identities it writes stay symbolic, and a copy is the value
# itself. The attributes and the classmethod int defines are named there too, since the
# derivation reads only methods called on a value (downgrades-class-body-taught-attributes-named).
# The tuples numbers holds name what is left to int on purpose, and the derivation at the bottom
# of the file downgrades every other method int defines. What each operation answers is tracked
# by the class numbers holds for its Python type.


def _itself(self: ConcolicInt) -> ConcolicInt:
    """An operation that changes nothing about an int: the value itself, so no node is added.

    `int(x)` is not one of them: Python copies whatever `__int__` hands
    back into a plain int, so it stays a downgrade (int-conversion-stays-a-downgrade).
    """
    return self


class ConcolicInt(int):
    """A real int with a name and a sink.

    The operations taught below stay symbolic. Any other operation is int's own and
    returns a plain value, with a downgrade in the sink naming what was lost.
    """

    expression: Expression
    sink: BranchSink
    # set on the int a tracked bool is (`bools._the_int`), whose expression is the bool's own
    # condition: what its text reads that condition as, the int it is
    as_int: Expression | None = None

    # Python swaps the operands of a reflected compare itself, so `10 < x` runs
    # `x.__gt__(10)` and prints [">", "x", 10]; nothing here has to reflect anything.
    # int promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    # Each operation on two numbers meets a float as Python's int does, through float's own
    # (see `numbers.promoted`), so `n < 2.5` is ["<", "n", 2.5] and `n + 0.5` a tracked float.
    # Each one Python would ask an int subclass on the right for first, it asks first too, the
    # derived downgrades among them (see `numbers.answered_first`)
    __lt__ = asked_first("__lt__", compare("<", *promoted(int.__lt__)))
    __le__ = asked_first("__le__", compare("<=", *promoted(int.__le__)))
    __gt__ = asked_first("__gt__", compare(">", *promoted(int.__gt__)))
    __ge__ = asked_first("__ge__", compare(">=", *promoted(int.__ge__)))
    __eq__ = asked_first("__eq__", compare("==", *promoted(int.__eq__)))
    __ne__ = asked_first("__ne__", compare("!=", *promoted(int.__ne__)))
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself
    # a pickle holds the plain value and loads as an int, and writing it is a downgrade
    __reduce_ex__, __reduce__ = pickled(int)

    __add__ = asked_first("__add__", numbers.arithmetic("+", *promoted(int.__add__)))
    __radd__ = numbers.arithmetic("+", *promoted(int.__radd__), reflected=True)
    __sub__ = asked_first("__sub__", numbers.arithmetic("-", *promoted(int.__sub__)))
    __rsub__ = numbers.arithmetic("-", *promoted(int.__rsub__), reflected=True)
    __mul__ = asked_first("__mul__", numbers.arithmetic("*", *promoted(int.__mul__)))
    __rmul__ = numbers.arithmetic("*", *promoted(int.__rmul__), reflected=True)
    # `/` answers a float even on two ints, which numbers tracks as a tracked float
    __truediv__ = asked_first("__truediv__", numbers.division("/", *promoted(int.__truediv__)))
    __rtruediv__ = numbers.division("/", *promoted(int.__rtruediv__), reflected=True)
    __floordiv__ = asked_first("__floordiv__", numbers.division("//", *promoted(int.__floordiv__)))
    __rfloordiv__ = numbers.division("//", *promoted(int.__rfloordiv__), reflected=True)
    __mod__ = asked_first("__mod__", numbers.division("%", *promoted(int.__mod__)))
    __rmod__ = numbers.division("%", *promoted(int.__rmod__), reflected=True)
    __divmod__ = asked_first("__divmod__", numbers.divmod_of(*promoted(int.__divmod__)))
    __rdivmod__ = numbers.divmod_of(*promoted(int.__rdivmod__), reflected=True)
    __neg__ = numbers.unary("-", int.__neg__)
    __abs__ = numbers.unary("abs", int.__abs__)
    # a float exponent is float's own answer, and a downgrade like any power it does not encode
    __pow__ = asked_first("__pow__", numbers.power(promoted(int.__pow__)[0]))
    __pos__ = _itself
    __index__ = _itself
    __trunc__ = _itself
    __floor__ = _itself
    __ceil__ = _itself
    __round__ = numbers.rounded(_itself)

    # its text is a tracked str, `["str", x]`, its decimal digits as int's repr writes them, and
    # so is a format with no spec; a spec pyct does not encode is int's own and a downgrade
    __str__ = texts.text(int.__repr__, lambda self: self.as_int or self.expression)
    __format__ = downgraded(int, "__format__", first=texts.alone(__str__))  # pyrefly: ignore[bad-override]

    # int's plain names that hand back the value itself, as `+x` does. `imag` and `denominator`
    # stay int's own constants, 0 and 1, and `is_integer` is kept; the rest are derived downgrades
    real = numbers.attribute(int.real, _itself)  # pyrefly: ignore[bad-override]
    numerator = numbers.attribute(int.numerator, _itself)  # pyrefly: ignore[bad-override]
    conjugate = numbers.itself(int.conjugate, _itself)
    as_integer_ratio = numbers.ratio(_itself)
    # int's own would build this class from the value alone
    from_bytes = built_plainly(int, "from_bytes")  # pyrefly: ignore[bad-override]

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> ConcolicInt:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # the int is the condition: zero is the one value that takes the other side
        return forked(self.sink, ["!=", self.expression, 0], own(int.__bool__, self))


# the class body above is everything ConcolicInt teaches. The rest of int differs only in the
# name it calls and records, so the derivation writes it. An int that Python computes is
# tracked as a ConcolicInt
downgrade_the_rest(ConcolicInt, int, kept=INT_KEPT, inherited=(), first=answered_first)
numbers.enter(int, ConcolicInt)
