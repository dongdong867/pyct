"""The concolic int: a real int that also carries its symbolic form."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, Self

from pyct.core import numbers, texts
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Expression
from pyct.core.counts import Count
from pyct.core.numbers import (
    INT_KEPT,
    answered_first,
    asked_first,
    compare,
    promoted,
)
from pyct.core.spans import Span, added, exactly, proves, scaled
from pyct.core.values import (
    REPORTED_CLASS,
    as_base,
    built_plainly,
    copy_as_itself,
    downgrade_the_rest,
    downgraded,
    forked,
    own,
    pickled,
    refused_delete,
    refused_set,
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


# the plain operands a length's range is carried through: an int, or a bool as the int it is
_PLAIN = (int, bool)


def _carried(op: str, name: str, *, reflected: bool = False) -> Callable[..., Any]:
    """A tracked int's `+`, `-` or `*` by its dunder ``name``, carrying the range of a length
    (``ConcolicInt.span``) through it where the other operand is a plain int, on either side.
    One asked of a number subclass on the right first is asked so (``asked_first``)."""
    method = numbers.arithmetic(op, *promoted(getattr(int, name)), reflected=reflected)

    def compute(self: ConcolicInt, other: object) -> Any:
        answer = method(self, other)
        span = self.span
        if span is not None and type(answer) is ConcolicInt and type(other) in _PLAIN:
            number = int.__int__(other)  # pyrefly: ignore[bad-argument-type]
            answer.__dict__["span"] = _through(op, span, number, reflected=reflected)
            if self.count is not None and type(other) is int:
                answer.__dict__["count"] = self.count.through(op, number, reflected=reflected)
        return answer

    return compute if reflected else asked_first(name, compute)


def _through(op: str, span: Span, number: int, *, reflected: bool) -> Span:
    """The range of ``length op number``, or of ``number op length`` when ``reflected``."""
    if op == "*":
        return scaled(span, number)
    if op == "+":
        return added(span, exactly(number))
    return added(scaled(span, -1), exactly(number)) if reflected else added(span, exactly(-number))


def _proven(op: str, name: str) -> Callable[..., Any]:
    """A tracked int's compare by its dunder ``name``, asked of a number subclass on the right
    first, answering a bool that records a fact where it is tested when the int carries a
    length's range that proves the answer against a plain int. A split's count reads its list's
    range as it is now, and a compare that range does not prove narrows it where it is tested
    (``core.counts``)."""
    method = compare(op, *promoted(getattr(int, name)))

    def compute(self: ConcolicInt, other: object) -> Any:
        answer = method(self, other)
        count = self.count
        span = self.span if count is None else (count.span() or self.span)
        if span is not None and type(answer) is ConcolicBool and type(other) in _PLAIN:
            number = int.__int__(other)  # pyrefly: ignore[bad-argument-type]
            if proves(span, op, number) is int.__bool__(answer):
                answer.__dict__["decided"] = True
            elif count is not None and type(other) is int:
                answer.__dict__["narrows"] = partial(count.narrow, op, number)
        return answer

    return asked_first(name, compute)


class ConcolicInt(int):
    """A real int with a name and a sink.

    The operations taught below stay symbolic. Any other operation is int's own and
    returns a plain value, with a downgrade in the sink naming what was lost.
    """

    expression: Expression
    sink: BranchSink
    # the base type, as `isinstance`, singledispatch and a class pattern read it
    __class__ = REPORTED_CLASS  # pyrefly: ignore[bad-override]
    # set on the int `len(x)` returns, the range ``x`` had at that call (see `core.spans`), and
    # carried through `+`, `-` and `*` with a plain int: a compare with a plain int it proves
    # is a fact where it is tested. An operation that hands back the int itself, as `+x` does,
    # keeps it; one that makes another int, `+`, `-` or `*` with any other operand among them,
    # makes one with none
    span: Span | None = None
    # set on the int `len(parts)` returns for a split's list, and carried through `+`, `-` and
    # `*` with a plain int: the link back to the list, whose range a compare with a plain int
    # narrows (see `core.counts`)
    count: Count | None = None
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
    __lt__ = _proven("<", "__lt__")
    __le__ = _proven("<=", "__le__")
    __gt__ = _proven(">", "__gt__")
    __ge__ = _proven(">=", "__ge__")
    __eq__ = _proven("==", "__eq__")
    __ne__ = _proven("!=", "__ne__")
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself
    # a pickle holds the plain value and loads as an int, and writing it is a downgrade
    __reduce_ex__, __reduce__ = pickled(int)

    __add__ = _carried("+", "__add__")
    __radd__ = _carried("+", "__radd__", reflected=True)
    __sub__ = _carried("-", "__sub__")
    __rsub__ = _carried("-", "__rsub__", reflected=True)
    __mul__ = _carried("*", "__mul__")
    __rmul__ = _carried("*", "__rmul__", reflected=True)
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

    # the class called with a value is int's own, a plain int; pyct builds a tracked one
    __new__ = as_base
    # a plain int takes no attribute: a set or a delete is Python's own refusal, pyct's names too
    __setattr__ = refused_set
    __delattr__ = refused_delete

    @classmethod
    def made(cls, value: int, expression: Expression, sink: BranchSink) -> Self:
        """A tracked int of this value and form: how pyct builds one."""
        made = int.__new__(cls, value)
        # the value refuses a set, as a plain one does, so pyct writes its fields straight in
        fields = made.__dict__
        fields["expression"] = expression
        fields["sink"] = sink
        return made

    def __bool__(self) -> bool:
        # the int is the condition: zero is the one value that takes the other side
        return forked(self.sink, ["!=", self.expression, 0], own(int.__bool__, self))


# the class body above is everything ConcolicInt teaches. The rest of int differs only in the
# name it calls and records, so the derivation writes it. An int that Python computes is
# tracked as a ConcolicInt
downgrade_the_rest(ConcolicInt, int, kept=INT_KEPT, inherited=(), first=answered_first)
numbers.enter(int, ConcolicInt)
