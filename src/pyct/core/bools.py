"""The concolic bool: what every concolic type answers a compare with.

A tracked bool is also a number, the int 1 or 0, as Python's bool is, so its
arithmetic and its compares are the ones a tracked int teaches, built from
numbers. What each answers is tracked by the class numbers holds for its
Python type, so this module never names the tracked int.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core import numbers, texts
from pyct.core.branch import BranchSink, Expression
from pyct.core.numbers import INT_KEPT, compare, promoted
from pyct.core.values import (
    built_plainly,
    copy_as_itself,
    downgrade_the_rest,
    downgraded,
    forked,
    own,
    pickled,
)


def _the_int(self: ConcolicBool) -> Any:
    """The int a bool is, 1 or 0, with the same condition: `+True` is 1, and adds no node.

    Its text reads the condition as that int, `["int", b]`, as `int(b)`
    writes it, since Python writes the int, `1`, where the bool writes `True`.
    """
    number = numbers.tracked(own(int.__index__, self), self.expression, self.sink)
    number.as_int = ["int", self.expression]
    return number


def _truth(other: object) -> Expression | None:
    """How `&`, `|` and `^` read the other side: a bool, tracked or plain, and nothing else."""
    if isinstance(other, ConcolicBool):
        return other.expression
    return other if isinstance(other, bool) else None


def _logical(
    op: str, name: str, *, reflected: bool = False
) -> Callable[[ConcolicBool, object], object]:
    """Python's `&`, `|` or `^` between two bools: a bool, on the conditions of both.

    A plain True or False is a literal, a tracked bool its condition. int's
    own operation answers an int even on two bools, so its answer is read as
    the bool it is, as a compare's is. The expression keeps Python's written
    order: a reflected method is called on the right operand, so `True & b`
    is ["&", true, b]. With an int on the other side it is int's bitwise
    operation, which stays a downgrade (follow-integers).
    """
    operation = getattr(int, name)
    downgrade = downgraded(int, name)

    def compute(self: ConcolicBool, other: object) -> object:
        form = _truth(other)
        if form is None:
            return downgrade(self, other)
        sides = [form, self.expression] if reflected else [self.expression, form]
        answer = bool(own(operation, self, other))
        return ConcolicBool(answer, expression=[op, *sides], sink=self.sink)

    return compute


def _written(self: ConcolicBool) -> str:
    """The bool's text, `True` or `False`, as bool's repr writes it."""
    # int.__bool__, not bool(self): bool() would record a fork
    return repr(int.__bool__(self))


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
    # teaches it, and meets a float as that int does (see `numbers.promoted`). int promises a
    # bool from a compare, and a ConcolicBool is an int that is not a bool; the override breaks
    # that promise on purpose, as ConcolicInt's does
    __lt__ = compare("<", *promoted(int.__lt__))
    __le__ = compare("<=", *promoted(int.__le__))
    __gt__ = compare(">", *promoted(int.__gt__))
    __ge__ = compare(">=", *promoted(int.__ge__))
    __eq__ = compare("==", *promoted(int.__eq__))
    __ne__ = compare("!=", *promoted(int.__ne__))
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself
    # a pickle holds the plain value and loads as a bool, and writing it is a downgrade
    __reduce_ex__, __reduce__ = pickled(bool)

    __add__ = numbers.arithmetic("+", *promoted(int.__add__))
    __radd__ = numbers.arithmetic("+", *promoted(int.__radd__), reflected=True)
    __sub__ = numbers.arithmetic("-", *promoted(int.__sub__))
    __rsub__ = numbers.arithmetic("-", *promoted(int.__rsub__), reflected=True)
    __mul__ = numbers.arithmetic("*", *promoted(int.__mul__))
    __rmul__ = numbers.arithmetic("*", *promoted(int.__rmul__), reflected=True)
    # `/` answers a float even on two ints, which numbers tracks as a tracked float
    __truediv__ = numbers.division("/", *promoted(int.__truediv__))
    __rtruediv__ = numbers.division("/", *promoted(int.__rtruediv__), reflected=True)
    __floordiv__ = numbers.division("//", *promoted(int.__floordiv__))
    __rfloordiv__ = numbers.division("//", *promoted(int.__rfloordiv__), reflected=True)
    __mod__ = numbers.division("%", *promoted(int.__mod__))
    __rmod__ = numbers.division("%", *promoted(int.__rmod__), reflected=True)
    __divmod__ = numbers.divmod_of(*promoted(int.__divmod__))
    __rdivmod__ = numbers.divmod_of(*promoted(int.__rdivmod__), reflected=True)
    __neg__ = numbers.unary("-", int.__neg__)
    __abs__ = numbers.unary("abs", int.__abs__)
    # a float exponent is float's own answer, and a downgrade like any power it does not encode
    __pow__ = numbers.power(promoted(int.__pow__)[0])
    __pos__ = _the_int
    __index__ = _the_int
    __trunc__ = _the_int
    __floor__ = _the_int
    __ceil__ = _the_int
    __round__ = numbers.rounded(_the_int)

    # int's plain names that hand back the number itself answer the int the bool is, as `+b`
    # does. Its constants and its downgrades are int's, and its classmethod is bool's own, as
    # plain Python answers `True.from_bytes(...)` with a bool
    real = numbers.attribute(int.real, _the_int)  # pyrefly: ignore[bad-override]
    numerator = numbers.attribute(int.numerator, _the_int)  # pyrefly: ignore[bad-override]
    conjugate = numbers.itself(int.conjugate, _the_int)
    as_integer_ratio = numbers.ratio(_the_int)
    from_bytes = built_plainly(bool, "from_bytes")  # pyrefly: ignore[bad-override]

    # `&`, `|` and `^` between two bools answer a bool, either way round; with an int, a downgrade
    __and__ = _logical("&", "__and__")  # pyrefly: ignore[bad-override]
    __or__ = _logical("|", "__or__")  # pyrefly: ignore[bad-override]
    __xor__ = _logical("^", "__xor__")  # pyrefly: ignore[bad-override]
    # Python asks for these only where a plain bool's own does not answer first, which is
    # where pyct substitutes `True & b` (`pyct.core.substitutes`)
    __rand__ = _logical("&", "__rand__", reflected=True)  # pyrefly: ignore[bad-override]
    __ror__ = _logical("|", "__ror__", reflected=True)  # pyrefly: ignore[bad-override]
    __rxor__ = _logical("^", "__rxor__", reflected=True)  # pyrefly: ignore[bad-override]

    # its text is a tracked str, `["str", b]`, `True` or `False` as bool's repr writes it, and so
    # is a format with no spec; a spec is the bool's own format and a downgrade
    __str__ = texts.text(_written)
    __format__ = downgraded(  # pyrefly: ignore[bad-override]
        int, "__format__", calling=_formatted, first=texts.alone(__str__)
    )

    def __new__(cls, value: bool, *, expression: Expression, sink: BranchSink) -> ConcolicBool:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        return forked(self.sink, self.expression, own(int.__bool__, self))

    __repr__ = _written  # pyrefly: ignore[bad-override]


# the class body above is everything ConcolicBool teaches. The rest of int differs only in the
# name it calls and records, so the derivation writes it. A bool that Python computes, a
# compare's answer among them, is tracked as a ConcolicBool
downgrade_the_rest(ConcolicBool, int, kept=INT_KEPT, inherited=())
numbers.enter(bool, ConcolicBool)
