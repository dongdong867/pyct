"""Concolic values: real Python values that also carry their symbolic form."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.branch import Branch, BranchSink, Downgrade, Expression, caller_site

# every value-producing int operation pyct has not taught. The comparisons, the truth test,
# the arithmetic and the identities below are taught and stay symbolic; `__hash__`,
# `__repr__`, the pickling hooks and the object plumbing (`__new__`, `__getattribute__`,
# `__sizeof__`) are not the target's path and stay int's, so a dict key and a debugger read
# cost nothing.
_UNTAUGHT = (
    "__truediv__",
    "__rtruediv__",
    "__floordiv__",
    "__rfloordiv__",
    "__mod__",
    "__rmod__",
    "__divmod__",
    "__rdivmod__",
    "__rpow__",
    "__lshift__",
    "__rlshift__",
    "__rshift__",
    "__rrshift__",
    "__and__",
    "__rand__",
    "__or__",
    "__ror__",
    "__xor__",
    "__rxor__",
    "__invert__",
    "__int__",
    "__float__",
    "__str__",
    "__format__",
)


# the mark that says a raise came out of the base type's own operation. The call that made it
# is the only code that knows, so it writes the mark there and blame reads it back
_TARGET_RAISE = "__pyct_target_raise__"


def _own[T](operation: Callable[..., T], *args: object) -> T:
    """The base type's own answer, with a raise out of it marked as the target's.

    Every call pyct makes into the base type goes through here, taught
    operation and downgrade alike. A raise under one of them is the target's
    program failing, not a pyct bug. Only an ``Exception`` is one: a deadline
    and a keyboard interrupt land here too, and neither is the operation's.
    """
    try:
        return operation(*args)
    except Exception as error:
        setattr(error, _TARGET_RAISE, True)
        raise


def raised_by_target(error: BaseException) -> bool:
    """Whether this raise came out of the base type's own operation."""
    return getattr(error, _TARGET_RAISE, False) is True


def _forked(sink: BranchSink, expression: Expression, taken: bool) -> bool:
    """Record the fork a truth test just took, and answer with the side it took.

    Python demands a real bool back from ``__bool__``, so neither class can
    answer with a value that carries the condition; the condition goes to the
    sink here instead. One helper, so both classes record it the same way.
    """
    sink.append(Branch(expression=expression, taken=taken, site=caller_site()))
    return taken


class ConcolicBool(int):
    """The result of a symbolic compare. Testing it for truth records the fork.

    It is an int the way `bool` is, because `bool` cannot be subclassed.
    """

    expression: Expression
    sink: BranchSink

    def __new__(cls, value: bool, *, expression: Expression, sink: BranchSink) -> ConcolicBool:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        return _forked(self.sink, self.expression, _own(int.__bool__, self))

    def __repr__(self) -> str:
        # int.__bool__, not bool(self): bool() would record a fork
        return repr(int.__bool__(self))


def _form_of(value: int) -> Expression:
    """The symbolic form of an operand: its expression if it has one, else itself."""
    return value.expression if isinstance(value, ConcolicInt) else value


def _compare(
    op: str, operation: Callable[[int, int], bool]
) -> Callable[[ConcolicInt, int], ConcolicBool]:
    """int's own answer to one comparison, carrying the condition that produced it.

    Now that `==` answers with a ConcolicBool, `x in [1, 2, 3]` and a dict
    lookup on a key that is equal without being the same one test that answer
    for truth, so each records a fork at the target's line.
    """

    def compare(self: ConcolicInt, other: int) -> ConcolicBool:
        # a bool is an int, but `x < True` is not a compare the solver has a leaf for;
        # a compare's value is a bool the same way
        if not isinstance(other, int) or isinstance(other, bool | ConcolicBool):
            return NotImplemented
        return ConcolicBool(
            bool(_own(operation, self, other)),
            expression=[op, self.expression, _form_of(other)],
            sink=self.sink,
        )

    return compare


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
        if not isinstance(other, int) or isinstance(other, bool | ConcolicBool):
            return NotImplemented
        operands = (
            [_form_of(other), self.expression] if reflected else [self.expression, _form_of(other)]
        )
        return ConcolicInt(_own(operation, self, other), expression=[op, *operands], sink=self.sink)

    return compute


def _unary(op: str, operation: Callable[[int], int]) -> Callable[[ConcolicInt], ConcolicInt]:
    """int's own answer to one unary operation, under the head the builtin or operator has."""

    def compute(self: ConcolicInt) -> ConcolicInt:
        return ConcolicInt(_own(operation, self), expression=[op, self.expression], sink=self.sink)

    return compute


def _downgraded(name: str) -> Callable[..., object]:
    """int's own operation, and a note in the sink that the condition was lost.

    The note comes after the call, so an operation that raises records
    nothing and the raise stays the target's. ``NotImplemented`` is not an
    answer either: the other operand's reflected method gets its turn, and
    only a real result is a lost condition.
    """
    operation = getattr(int, name)

    def downgrade(self: ConcolicInt, *args: object) -> object:
        result = _own(operation, self, *args)
        if result is not NotImplemented:
            self.sink.append(Downgrade(name=name))
        return result

    return downgrade


# cvc5 takes `^` with a constant exponent only, and refuses to parse one at this bound or
# above. Parsing is all the bound promises: how long the solve takes is the budget's business,
# as for any nonlinear fork, and a run with no budget can wait on a large power.
_POWER_LIMIT = 67_108_864
_POWER_DOWNGRADE = _downgraded("__pow__")


def _power(self: ConcolicInt, exponent: object, modulus: object = None) -> object:
    """A constant power keeps the condition; every other power is int's own and a downgrade.

    A plain int exponent from zero up to cvc5's bound is what `^` encodes. A
    concolic, negative or bool exponent, a float, and a third argument all
    fall to int's own answer.
    """
    if modulus is None and type(exponent) is int and 0 <= exponent < _POWER_LIMIT:
        return ConcolicInt(
            _own(int.__pow__, self, exponent),
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


_ROUND_DOWNGRADE = _downgraded("__round__")


def _round(self: ConcolicInt, ndigits: object = None) -> object:
    """Rounding an int to zero or more digits is the int itself; to a power of ten, it is not."""
    if ndigits is None or (type(ndigits) is int and ndigits >= 0):
        return self
    return _ROUND_DOWNGRADE(self, ndigits)


class ConcolicInt(int):
    """A real int with a name and a sink.

    The six comparisons, the truth test and the arithmetic below are symbolic.
    Any other operation is int's own and returns a plain value, with a
    downgrade in the sink naming what was lost.
    """

    expression: Expression
    sink: BranchSink

    # Python swaps the operands of a reflected compare itself, so `10 < x` runs
    # `x.__gt__(10)` and prints [">", "x", 10]; nothing here has to reflect anything.
    # int promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    __lt__ = _compare("<", int.__lt__)  # pyrefly: ignore[bad-override]
    __le__ = _compare("<=", int.__le__)  # pyrefly: ignore[bad-override]
    __gt__ = _compare(">", int.__gt__)  # pyrefly: ignore[bad-override]
    __ge__ = _compare(">=", int.__ge__)  # pyrefly: ignore[bad-override]
    __eq__ = _compare("==", int.__eq__)  # pyrefly: ignore[bad-override]
    __ne__ = _compare("!=", int.__ne__)  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = int.__hash__

    __add__ = _arithmetic("+", int.__add__)
    __radd__ = _arithmetic("+", int.__radd__, reflected=True)
    __sub__ = _arithmetic("-", int.__sub__)
    __rsub__ = _arithmetic("-", int.__rsub__, reflected=True)
    __mul__ = _arithmetic("*", int.__mul__)
    __rmul__ = _arithmetic("*", int.__rmul__, reflected=True)
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
        return _forked(self.sink, ["!=", self.expression, 0], _own(int.__bool__, self))


# forty-odd methods that differ only in the name they call and record, so a loop writes them
for _name in _UNTAUGHT:
    setattr(ConcolicInt, _name, _downgraded(_name))
