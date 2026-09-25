"""The concolic int: a real int that also carries its symbolic form."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.bools import ConcolicBool, compare
from pyct.core.branch import BranchSink, Expression
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own

# the `ConcolicInt` body below is the taught set: the comparisons, the truth test, the
# arithmetic, the division and the identities it writes stay symbolic, and a copy is the value
# itself. The three tuples here name what is left to int on purpose, and the derivation at the
# bottom of the file downgrades every other method int defines.

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

# int's plain methods record nothing yet. The ticket that wraps them is
# `report-a-plain-int-method-as-a-downgrade`; until it lands, these stay int's own
_NOT_YET = (
    "as_integer_ratio",
    "bit_count",
    "bit_length",
    "conjugate",
    "is_integer",
    "to_bytes",
)

# int inherits `__str__` from object, so reading what int itself defines never reaches it, and
# `print(x)` still drops the condition
_INHERITED = ("__str__",)


def _operand(other: object) -> Expression | None:
    """The symbolic form of an operand int takes, or None for one it does not.

    The form is the operand's expression if it has one, else the operand itself.
    """
    # a bool is an int, but `x < True` is not a compare the solver has a leaf for;
    # a compare's value is a bool the same way
    if not isinstance(other, int) or isinstance(other, bool | ConcolicBool):
        return None
    return other.expression if isinstance(other, ConcolicInt) else other


def _operands(self: ConcolicInt, form: Expression, *, reflected: bool) -> list[Expression]:
    """The two sides in Python's written order: a reflected method ran on the right one."""
    return [form, self.expression] if reflected else [self.expression, form]


def _arithmetic(
    op: str, operation: Callable[[int, int], int], *, reflected: bool = False
) -> Callable[[ConcolicInt, int], ConcolicInt]:
    """int's own answer to one arithmetic operation, carrying the expression that built it.

    The expression keeps Python's written order: a reflected method is
    called on the right operand, so `10 - x` is ["-", 10, "x"]. A bool on
    the other side is not an operand the solver has a leaf for, and gets
    NotImplemented the way the compares give it, so Python answers with
    int's own plain value; follow-booleans owns it.
    """

    def compute(self: ConcolicInt, other: int) -> ConcolicInt:
        form = _operand(other)
        if form is None:
            return NotImplemented
        operands = _operands(self, form, reflected=reflected)
        return ConcolicInt(own(operation, self, other), expression=[op, *operands], sink=self.sink)

    return compute


def _zero_fork(divisor: int) -> None:
    """The fork a symbolic divisor takes on its way into a division: `["!=", divisor, 0]`.

    Testing it for truth is what records it, so `ConcolicInt.__bool__` and
    `forked` stay the one place a fork is written. A plain int divisor has
    nothing to flip and records nothing.
    """
    if isinstance(divisor, ConcolicInt):
        bool(divisor)


def _division(
    op: str, operation: Callable[[int, int], int], *, reflected: bool = False
) -> Callable[[ConcolicInt, int], ConcolicInt]:
    """int's own answer to one division, with the zero fork recorded before the call.

    The fork goes in first, where `downgraded` notes its loss after the
    call; a division is the one operation whose fork is about whether the
    call raises at all. `execute` keeps what the sink held when the raise
    happened, so recording it first is what lets the crashing input's line
    list the fork it died on. It also puts `divisor != 0` earlier in the
    prefix of every solver query that divides by a symbolic divisor, where
    SMT-LIB leaves division by zero uninterpreted.
    """

    def compute(self: ConcolicInt, other: int) -> ConcolicInt:
        form = _operand(other)
        if form is None:
            return NotImplemented
        _zero_fork(self if reflected else other)
        operands = _operands(self, form, reflected=reflected)
        return ConcolicInt(own(operation, self, other), expression=[op, *operands], sink=self.sink)

    return compute


def _divmod(
    *, reflected: bool = False
) -> Callable[[ConcolicInt, int], tuple[ConcolicInt, ConcolicInt]]:
    """int's own divmod: the quotient and the remainder, each carrying its own expression.

    One call divides once, so it records one zero fork, where `x // y` and
    `x % y` written out would record two.
    """
    operation = int.__rdivmod__ if reflected else int.__divmod__

    def compute(self: ConcolicInt, other: int) -> tuple[ConcolicInt, ConcolicInt]:
        form = _operand(other)
        if form is None:
            return NotImplemented
        _zero_fork(self if reflected else other)
        operands = _operands(self, form, reflected=reflected)
        quotient, remainder = own(operation, self, other)
        return (
            ConcolicInt(quotient, expression=["//", *operands], sink=self.sink),
            ConcolicInt(remainder, expression=["%", *operands], sink=self.sink),
        )

    return compute


def _unary(op: str, operation: Callable[[int], int]) -> Callable[[ConcolicInt], ConcolicInt]:
    """int's own answer to one unary operation, under the head the builtin or operator has."""

    def compute(self: ConcolicInt) -> ConcolicInt:
        return ConcolicInt(own(operation, self), expression=[op, self.expression], sink=self.sink)

    return compute


# cvc5 takes `^` with a constant exponent only, and refuses to parse one at this bound or
# above. Parsing is all the bound promises: how long the solve takes is the budget's business,
# as for any nonlinear fork, and a run with no budget can wait on a large power.
_POWER_LIMIT = 67_108_864
_POWER_DOWNGRADE = downgraded(int, "__pow__")


def _power(self: ConcolicInt, exponent: object, modulus: object = None) -> object:
    """A constant power keeps the condition; every other power is int's own and a downgrade.

    A plain int exponent from zero up to cvc5's bound is what `^` encodes. A
    concolic, negative or bool exponent, a float, and a third argument all
    fall to int's own answer.
    """
    if modulus is None and type(exponent) is int and 0 <= exponent < _POWER_LIMIT:
        return ConcolicInt(
            own(int.__pow__, self, exponent),
            expression=["**", self.expression, exponent],
            sink=self.sink,
        )
    return _POWER_DOWNGRADE(self, exponent, modulus)


def _itself(self: ConcolicInt) -> ConcolicInt:
    """An operation that changes nothing about an int: the value itself, so no node is added.

    `int(x)` is not one of them: Python copies whatever `__int__` hands
    back into a plain int, so it stays a downgrade (int-conversion-stays-a-downgrade).
    """
    return self


_ROUND_DOWNGRADE = downgraded(int, "__round__")


def _round(self: ConcolicInt, ndigits: object = None) -> object:
    """Rounding an int to zero or more digits is the int itself; to a power of ten, it is not."""
    if ndigits is None or (type(ndigits) is int and ndigits >= 0):
        return self
    return _ROUND_DOWNGRADE(self, ndigits)


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
    __lt__ = compare("<", int.__lt__, _operand)  # pyrefly: ignore[bad-override]
    __le__ = compare("<=", int.__le__, _operand)  # pyrefly: ignore[bad-override]
    __gt__ = compare(">", int.__gt__, _operand)  # pyrefly: ignore[bad-override]
    __ge__ = compare(">=", int.__ge__, _operand)  # pyrefly: ignore[bad-override]
    __eq__ = compare("==", int.__eq__, _operand)  # pyrefly: ignore[bad-override]
    __ne__ = compare("!=", int.__ne__, _operand)  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

    __add__ = _arithmetic("+", int.__add__)
    __radd__ = _arithmetic("+", int.__radd__, reflected=True)
    __sub__ = _arithmetic("-", int.__sub__)
    __rsub__ = _arithmetic("-", int.__rsub__, reflected=True)
    __mul__ = _arithmetic("*", int.__mul__)
    __rmul__ = _arithmetic("*", int.__rmul__, reflected=True)
    __floordiv__ = _division("//", int.__floordiv__)
    __rfloordiv__ = _division("//", int.__rfloordiv__, reflected=True)
    __mod__ = _division("%", int.__mod__)
    __rmod__ = _division("%", int.__rmod__, reflected=True)
    __divmod__ = _divmod()
    __rdivmod__ = _divmod(reflected=True)
    __neg__ = _unary("-", int.__neg__)
    __abs__ = _unary("abs", int.__abs__)
    # int promises an int or a float from a power; a downgraded one is int's own, but a kept
    # one is a ConcolicInt, and the union is not what int declared
    __pow__ = _power  # pyrefly: ignore[bad-override]
    __pos__ = _itself
    __index__ = _itself
    __trunc__ = _itself
    __floor__ = _itself
    __ceil__ = _itself
    __round__ = _round  # pyrefly: ignore[bad-override]

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> ConcolicInt:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # the int is the condition: zero is the one value that takes the other side
        return forked(self.sink, ["!=", self.expression, 0], own(int.__bool__, self))


# the class body above is everything ConcolicInt teaches. The rest of int, and the `__str__`
# int inherits, differ only in the name they call and record, so the derivation writes them
downgrade_the_rest(ConcolicInt, int, kept=_KEPT + _NOT_YET, inherited=_INHERITED)
