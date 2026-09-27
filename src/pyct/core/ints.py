"""The concolic int: a real int that also carries its symbolic form."""

from __future__ import annotations

from pyct.core import numbers
from pyct.core.branch import BranchSink, Expression
from pyct.core.numbers import INT_INHERITED, INT_KEPT, INT_NOT_YET, compare, operand
from pyct.core.values import copy_as_itself, downgrade_the_rest, forked, own, pickled

# the `ConcolicInt` body below is the taught set: the comparisons, the truth test, the
# arithmetic, the division and the identities it writes stay symbolic, and a copy is the value
# itself. The tuples numbers holds name what is left to int on purpose, and the derivation at
# the bottom of the file downgrades every other method int defines. What each operation
# answers is tracked by the class numbers holds for its Python type.


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

    # Python swaps the operands of a reflected compare itself, so `10 < x` runs
    # `x.__gt__(10)` and prints [">", "x", 10]; nothing here has to reflect anything.
    # int promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    __lt__ = compare("<", int.__lt__, operand)
    __le__ = compare("<=", int.__le__, operand)
    __gt__ = compare(">", int.__gt__, operand)
    __ge__ = compare(">=", int.__ge__, operand)
    __eq__ = compare("==", int.__eq__, operand)
    __ne__ = compare("!=", int.__ne__, operand)
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself
    # a pickle holds the plain value and loads as an int, and writing it is a downgrade
    __reduce_ex__, __reduce__ = pickled(int)

    __add__ = numbers.arithmetic("+", int.__add__)
    __radd__ = numbers.arithmetic("+", int.__radd__, reflected=True)
    __sub__ = numbers.arithmetic("-", int.__sub__)
    __rsub__ = numbers.arithmetic("-", int.__rsub__, reflected=True)
    __mul__ = numbers.arithmetic("*", int.__mul__)
    __rmul__ = numbers.arithmetic("*", int.__rmul__, reflected=True)
    __floordiv__ = numbers.division("//", int.__floordiv__)
    __rfloordiv__ = numbers.division("//", int.__rfloordiv__, reflected=True)
    __mod__ = numbers.division("%", int.__mod__)
    __rmod__ = numbers.division("%", int.__rmod__, reflected=True)
    __divmod__ = numbers.divmod_of(int.__divmod__)
    __rdivmod__ = numbers.divmod_of(int.__rdivmod__, reflected=True)
    __neg__ = numbers.unary("-", int.__neg__)
    __abs__ = numbers.unary("abs", int.__abs__)
    __pow__ = numbers.power(int.__pow__)
    __pos__ = _itself
    __index__ = _itself
    __trunc__ = _itself
    __floor__ = _itself
    __ceil__ = _itself
    __round__ = numbers.rounded(_itself)

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> ConcolicInt:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # the int is the condition: zero is the one value that takes the other side
        return forked(self.sink, ["!=", self.expression, 0], own(int.__bool__, self))


# the class body above is everything ConcolicInt teaches. The rest of int, and the `__str__`
# int inherits, differ only in the name they call and record, so the derivation writes them.
# An int that Python computes is tracked as a ConcolicInt
downgrade_the_rest(ConcolicInt, int, kept=INT_KEPT + INT_NOT_YET, inherited=INT_INHERITED)
numbers.enter(int, ConcolicInt)
