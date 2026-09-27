"""The concolic bool: what every concolic type answers a compare with.

A tracked bool is also a number, the int 1 or 0, as Python's bool is, so its
arithmetic and its compares are the ones a tracked int teaches, built from
numbers. What each answers is tracked by the class numbers holds for its
Python type, so this module never names the tracked int.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core import numbers
from pyct.core.branch import BranchSink, Expression
from pyct.core.numbers import INT_INHERITED, INT_KEPT, INT_NOT_YET, compare, operand
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own


def _the_int(self: ConcolicBool) -> Any:
    """The int a bool is, 1 or 0, with the same condition: `+True` is 1, and adds no node."""
    return numbers.tracked(own(int.__index__, self), self.expression, self.sink)


def _truth(other: object) -> Expression | None:
    """How `&`, `|` and `^` read the other side: a bool, tracked or plain, and nothing else."""
    if isinstance(other, ConcolicBool):
        return other.expression
    return other if isinstance(other, bool) else None


def _logical(op: str, name: str) -> Callable[[ConcolicBool, object], object]:
    """Python's `&`, `|` or `^` between two bools: a bool, on the conditions of both.

    A plain True or False is a literal, a tracked bool its condition. int's
    own operation answers an int even on two bools, so its answer is read as
    the bool it is, as a compare's is. With an int on the other side it is
    int's bitwise operation, which stays a downgrade (follow-integers).
    """
    followed = compare(op, getattr(int, name), _truth)
    downgrade = downgraded(int, name)

    def compute(self: ConcolicBool, other: object) -> object:
        answer = followed(self, other)
        return downgrade(self, other) if answer is NotImplemented else answer

    return compute


def _formatted(self: ConcolicBool, spec: str) -> str:
    """How Python formats the bool this is: `True` with no spec, as the int 1 with one."""
    # int.__bool__, not bool(self): bool() would record a fork
    return format(int.__bool__(self), spec)


class ConcolicBool(int):
    """The result of a symbolic compare. Testing it for truth records the fork.

    It is an int the way `bool` is, because `bool` cannot be subclassed. The
    operations taught below stay symbolic. Any other operation is int's own
    and returns a plain value, with a downgrade in the sink naming what was
    lost.
    """

    expression: Expression
    sink: BranchSink

    # a compare or an arithmetic operation reads the bool as the int 1 or 0, as a tracked int
    # teaches it. int promises a bool from a compare, and a ConcolicBool is an int that is not
    # a bool; the override breaks that promise on purpose, as ConcolicInt's does
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
    __pos__ = _the_int
    __index__ = _the_int
    __trunc__ = _the_int
    __floor__ = _the_int
    __ceil__ = _the_int
    __round__ = numbers.rounded(_the_int)

    # `&`, `|` and `^` between two bools answer a bool; with an int, a downgrade
    __and__ = _logical("&", "__and__")  # pyrefly: ignore[bad-override]
    __or__ = _logical("|", "__or__")  # pyrefly: ignore[bad-override]
    __xor__ = _logical("^", "__xor__")  # pyrefly: ignore[bad-override]

    # the text drops the condition, so it stays a downgrade, but it is the bool's text. An
    # f-string records this one entry: int's own would read `__str__` first
    __format__ = downgraded(int, "__format__", calling=_formatted)  # pyrefly: ignore[bad-override]

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


# the class body above is everything ConcolicBool teaches. The rest of int, and the `__str__`
# int inherits, differ only in the name they call and record, so the derivation writes them.
# A bool that Python computes, a compare's answer among them, is tracked as a ConcolicBool
downgrade_the_rest(ConcolicBool, int, kept=INT_KEPT + INT_NOT_YET, inherited=INT_INHERITED)
numbers.enter(bool, ConcolicBool)
