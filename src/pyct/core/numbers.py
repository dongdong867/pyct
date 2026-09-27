"""What the tracked numbers share: which class tracks a result, how an operand reads, and
the operations they teach.

A result's own Python type picks its tracked class. pyct lets the base type
compute the plain answer, and `tracked` wraps it in the class entered for
that answer's type: `int.__add__` on two compares answers an int, so the sum
is a tracked int, and `int.__lt__` answers a bool, so a compare is a tracked
bool. pyct never restates Python's rule for which type an operation gives.

Each number module defines its class and enters it at its bottom, with
`enter`. So no number module imports another, and this module names none of
their classes. `pyct.core` imports every number module, so the table is full
before any value is built; a result whose type nothing entered raises
`LookupError` rather than coming back plain. The tracked str enters its
class too, as a result and not a number, so a number's text is tracked
(`pyct.core.texts`) without a number module importing `pyct.core.strs`.

The registry is two functions: `enter(base, cls)` and `tracked(value,
expression, sink)`. `operand` is the int family's rule, a tracked int's and
a tracked bool's: it takes an int or a bool alone, as int's own operations
do, and it is how a float reads an int or a bool too. `promoted` widens it
for a tracked int or bool, which meets a float as Python's int does.
`compare`, `arithmetic`, `division` and `divmod_of` serve every number type
and read the other side by the rule their caller passes, the int family's
by default. `itself`, `ratio` and `attribute` serve the plain names whose
answer is the value itself, such as `x.conjugate()` and `x.real`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.values import downgraded, own

# what a tracked int, and a tracked bool with it, leaves to int on purpose. A bool is the int 1
# or 0, so both keep the same names, and both derivations read them here. Each derivation
# downgrades every other method int defines.

# not the target's path: `__hash__`, `__repr__`, `__getnewargs__`, which pickle no longer calls
# once `__reduce_ex__` is taught, and the rest of the object plumbing, so a dict key and a
# debugger read cost nothing. `__getattribute__` is kept for a harder reason: the downgrade
# wrapper reads `self.sink`, which goes through `__getattribute__` itself, so a wrapped one
# recurses on the first attribute read. `is_integer` is kept because its answer is a constant,
# True for every int, so it reads nothing of the value and loses no condition
INT_KEPT = (
    "__hash__",
    "__repr__",
    "__getnewargs__",
    "__new__",
    "__getattribute__",
    "__sizeof__",
    "is_integer",
)


class Number(Protocol):
    """A tracked value: all an operation here needs of the type it is set on."""

    expression: Expression
    sink: BranchSink


# the tracked class for each Python type a result can have, and the classes themselves
_TRACKED: dict[type, type] = {}
_CLASSES: set[type] = set()


def enter(base: type, tracked_class: type, *, number: bool = True) -> None:
    """Make `tracked_class` the tracked form of every result whose type is exactly `base`.

    Each number module calls this once, at its bottom, for the class it
    defines, and so does `pyct.core.strs` with ``number=False``: a tracked
    str is a result a number's text gives, and never an operand an operation
    on numbers reads. A second class for the same type would make the answer
    depend on import order, so it raises.
    """
    if _TRACKED.get(base, tracked_class) is not tracked_class:
        raise ValueError(f"{base.__name__} is already tracked by {_TRACKED[base].__name__}")
    _TRACKED[base] = tracked_class
    if number:
        _CLASSES.add(tracked_class)


def tracked(value: object, expression: Expression, sink: BranchSink) -> Any:
    """A plain result as the tracked class its own type entered, carrying the expression.

    A type nothing entered raises: a module pyct.core did not import, or a
    type whose follow story has not shipped, fails here where it happens,
    never as a quietly plain value.
    """
    tracked_class: Any = _TRACKED.get(type(value))
    if tracked_class is None:
        raise LookupError(
            f"no tracked type is entered for {type(value).__name__}; "
            "pyct.core imports each number module so that each enters its class"
        )
    return tracked_class.made(value, expression, sink)


def operand(other: object) -> Expression | None:
    """How an int or a bool reads the other side of an operation, or None for one it does not take.

    It takes the int family alone. A tracked int or bool reads as its
    expression. A plain int reads as itself, and so does a plain bool, the
    int 1 or 0, as the literal True or False. An int of the target's own
    subclass, an IntEnum member say, reads as the plain int it equals: pyct
    writes the expression later, and the object kept as it is would run the
    target's own methods then. `int.__index__` is int's own, so it reads the
    value without calling any method the subclass defines. One whose own
    reflected operation Python asks first is asked before this rule is read
    (see `asked_first`). Any other value, a tracked number of another type
    included, is None, so the operation answers NotImplemented and Python
    asks the other operand.
    """
    if not isinstance(other, int):
        return None
    if type(other) in _CLASSES:
        return cast(Number, other).expression
    return other if type(other) is int or type(other) is bool else int.__index__(other)


def plain_int(value: object) -> object:
    """A tracked int or bool as the plain int it holds, and any other value as itself.

    float's own operation takes an int this way, and a bool is the int 1 or
    0 to it. CPython compares a float with an int wider than 48 bits by
    calling the int's own methods, so a tracked int handed to it would
    record forks and downgrades the target never wrote; the plain int has
    the same value and records nothing.
    """
    if type(value) in (_TRACKED.get(int), _TRACKED.get(bool)):
        return int.__index__(cast(int, value))
    return value


# the compares Python asks the right operand for, swapped, when the left one answers
# NotImplemented: `n < f` is `f > n`
_SWAPPED = {
    "__lt__": "__gt__",
    "__le__": "__ge__",
    "__gt__": "__lt__",
    "__ge__": "__le__",
    "__eq__": "__eq__",
    "__ne__": "__ne__",
}


def _mirrored(name: str) -> str:
    """The name of what Python asks the other operand for: `__radd__` for `__add__`, and back."""
    if name in _SWAPPED:
        return _SWAPPED[name]
    return f"__{name[3:]}" if name.startswith("__r") else f"__r{name[2:]}"


# each operation int defines on two operands, and the reflected one Python asks an int subclass
# on the right for first when that subclass defines it otherwise than int
_REFLECTED = {
    **_SWAPPED,
    "__add__": "__radd__",
    "__sub__": "__rsub__",
    "__mul__": "__rmul__",
    "__truediv__": "__rtruediv__",
    "__floordiv__": "__rfloordiv__",
    "__mod__": "__rmod__",
    "__divmod__": "__rdivmod__",
    "__pow__": "__rpow__",
    "__lshift__": "__rlshift__",
    "__rshift__": "__rrshift__",
    "__and__": "__rand__",
    "__or__": "__ror__",
    "__xor__": "__rxor__",
}


def answered_first(name: str, self: object, other: object) -> object:
    """What a number subclass on the right of a tracked int answers, as Python asks it, or
    NotImplemented.

    Python asks the right operand's reflected operation first when its type
    is a subclass of the left one's that defines that operation otherwise:
    `x > r` runs `type(r).__lt__` when the target's own class of `r` defines
    one. int declines every float, so Python asks a float subclass next, and
    it answers the same way: `x + g` runs `type(g).__radd__` when that is not
    float's own. A tracked int stands where the target's plain int would, so
    pyct asks either one too, before anything of int's runs (see
    `reflected_answer`). A tracked bool or float asks an int subclass
    nothing, as Python's bool and float do not: an int subclass subclasses
    neither.
    """
    reflected = _REFLECTED.get(name)
    base = int if isinstance(other, int) else float if isinstance(other, float) else None
    kind = type(other)
    if reflected is None or base is None or kind in (base, bool, *_CLASSES):
        return NotImplemented
    operation = getattr(kind, reflected, None)
    if operation is None or operation is getattr(base, reflected, None):
        return NotImplemented
    return reflected_answer(name, self, other, operation)


def reflected_answer(
    name: str, self: object, other: object, operation: Callable[..., object]
) -> object:
    """The right operand's own reflected operation, asked first as Python asks it, on a tracked
    number on the left.

    Its answer is the answer. A plain one has lost the tracked number's
    condition, so the operation is named as a downgrade, as every loss is;
    a tracked one, and NotImplemented, which hands the operation back,
    record nothing. Each number type that asks a subclass first answers
    through here.
    """
    answer = own(operation, other, self)
    if answer is not NotImplemented and type(answer) not in _CLASSES:
        cast(Number, self).sink.append(Downgrade(name=name))
    return answer


def asked_first(name: str, method: Callable[..., Any]) -> Callable[..., Any]:
    """A tracked int's operation by that name, asked of a number subclass on the right first.

    See `answered_first`. Python asks the right operand first only for a
    call on one operand, so a three-argument `pow` goes to `method` alone.
    """

    def compute(self: object, other: object, /, *rest: object) -> Any:
        if not rest and (answer := answered_first(name, self, other)) is not NotImplemented:
            return answer
        return method(self, other, *rest)

    return compute


type Rule = Callable[[object], Expression | None]


def promoted(operation: Callable[..., object]) -> tuple[Callable[..., object], Rule]:
    """int's own operation widened to a float on the other side, and the rule that reads it.

    A tracked int and a tracked bool both take it, as Python's int and bool
    both meet a float. Python's int answers NotImplemented for a float, and
    the float's own mirrored operation answers instead, the int converted as
    Python converts it. So the answer here is that one: `n + 0.5` is
    `float.__radd__(0.5, n)`, on the int's plain value (see `plain_int`).
    The rule reads a tracked float as its expression, and any other float as
    a literal of its plain value. A float subclass that defines the mirrored
    operation otherwise than float is neither: the answer and the rule are
    NotImplemented and None, and Python asks the subclass, as it would for a
    plain int. A tracked int has asked it already when it answers
    (`answered_first`), so Python asks it again only once it has declined.
    """
    name = _mirrored(operation.__name__)
    mirror = getattr(float, name)

    def floats_own(other: object, *rest: object) -> bool:
        # a tracked float's mirror is followed, and float's own answers it. A three-argument
        # pow is the subclass's own when it defines either power, since Python's power slot is
        # then its own
        kind = type(other)
        if kind is float or kind in _CLASSES:
            return True
        names = (name, _mirrored(name)) if rest else (name,)
        return all(getattr(kind, each) is getattr(float, each) for each in names)

    def answer(self: object, other: object, /, *rest: object) -> object:
        if not isinstance(other, float):
            return operation(self, other, *rest)
        if not floats_own(other, *rest):
            return NotImplemented
        return mirror(other, plain_int(self), *rest)

    def rule(other: object) -> Expression | None:
        if not isinstance(other, float):
            return operand(other)
        if type(other) in _CLASSES:
            return cast(Number, other).expression
        return float.__float__(other) if floats_own(other) else None

    return answer, rule


def zero_fork(divisor: object) -> None:
    """The fork a tracked divisor takes on its way into a division, as `if` would test it.

    Testing it for truth is what records it, so each type's `__bool__` and
    `forked` stay the one place a fork is written: an int's is
    `["!=", divisor, 0]`, a bool's is its own condition. A plain divisor has
    nothing to flip and records nothing.
    """
    if type(divisor) in _CLASSES:
        bool(divisor)


def compare(
    op: str, operation: Callable[..., object], rule: Rule
) -> Callable[[Number, object], Any]:
    """The base type's own answer to one comparison, carrying the condition that produced it.

    `rule` is the concolic type's rule for the other side: the symbolic form
    of an operand the type takes, or None for one it does not. None answers
    NotImplemented, so the other operand gets its turn. Every concolic type
    answers a compare with a tracked bool.

    Now that `==` answers with a tracked bool, `x in [1, 2, 3]` and a dict
    lookup on a key that is equal without being the same one test that answer
    for truth, so each records a fork at the target's line.
    """

    def compute(self: Number, other: object) -> Any:
        form = rule(other)
        if form is None:
            return NotImplemented
        answer = bool(own(operation, self, other))
        return tracked(answer, [op, self.expression, form], self.sink)

    return compute


def _sides(self: Number, form: Expression, *, reflected: bool) -> list[Expression]:
    """The two sides in Python's written order: a reflected method ran on the right one."""
    return [form, self.expression] if reflected else [self.expression, form]


def arithmetic(
    op: str, operation: Callable[..., object], rule: Rule = operand, *, reflected: bool = False
) -> Callable[[Number, object], Any]:
    """The base type's own answer to one arithmetic operation, carrying the expression.

    The expression keeps Python's written order: a reflected method is
    called on the right operand, so `10 - x` is ["-", 10, "x"]. `rule`
    reads the other side, as `compare`'s does.
    """

    def compute(self: Number, other: object) -> Any:
        form = rule(other)
        if form is None:
            return NotImplemented
        expression = [op, *_sides(self, form, reflected=reflected)]
        return tracked(own(operation, self, other), expression, self.sink)

    return compute


def division(
    op: str, operation: Callable[..., object], rule: Rule = operand, *, reflected: bool = False
) -> Callable[[Number, object], Any]:
    """The base type's own answer to one division, with the zero fork recorded before the call.

    The fork goes in first, where `downgraded` notes its loss after the
    call; a division is the one operation whose fork is about whether the
    call raises at all. `execute` keeps what the sink held when the raise
    happened, so recording it first is what lets the crashing input's line
    list the fork it died on. It also puts `divisor != 0` earlier in the
    prefix of every solver query that divides by a symbolic divisor, where
    SMT-LIB leaves division by zero uninterpreted. `rule` reads the other
    side, as `compare`'s does.
    """

    def compute(self: Number, other: object) -> Any:
        form = rule(other)
        if form is None:
            return NotImplemented
        zero_fork(self if reflected else other)
        expression = [op, *_sides(self, form, reflected=reflected)]
        return tracked(own(operation, self, other), expression, self.sink)

    return compute


def divmod_of(
    operation: Callable[..., object], rule: Rule = operand, *, reflected: bool = False
) -> Callable[[Number, object], Any]:
    """The base type's own divmod: the quotient and the remainder, each carrying its expression.

    One call divides once, so it records one zero fork, where `x // y` and
    `x % y` written out would record two. `rule` reads the other side, as
    `compare`'s does.
    """

    def compute(self: Number, other: object) -> Any:
        form = rule(other)
        if form is None:
            return NotImplemented
        zero_fork(self if reflected else other)
        sides = _sides(self, form, reflected=reflected)
        quotient, remainder = cast(tuple[object, object], own(operation, self, other))
        whole = tracked(quotient, ["//", *sides], self.sink)
        return whole, tracked(remainder, ["%", *sides], self.sink)

    return compute


def unary(op: str, operation: Callable[[Any], object]) -> Callable[[Number], Any]:
    """The base type's own answer to one unary operation, under the head it has."""

    def compute(self: Number) -> Any:
        return tracked(own(operation, self), [op, self.expression], self.sink)

    return compute


# cvc5 takes `^` with a constant exponent only, and refuses to parse one at this bound or
# above. Parsing is all the bound promises: how long the solve takes is the budget's business,
# as for any nonlinear fork, and a run with no budget can wait on a large power.
_POWER_LIMIT = 67_108_864


def power(operation: Callable[..., object]) -> Callable[..., Any]:
    """A constant power keeps the condition; every other power is the base's own and a downgrade.

    A plain int exponent from zero up to cvc5's bound is what `^` encodes,
    and so is a plain bool, the int 1 or 0. A tracked or negative exponent,
    a float, and a third argument all fall to the base type's own answer.
    """
    downgrade = downgraded(int, "__pow__", calling=operation)

    def compute(self: Number, exponent: object, modulus: object = None) -> Any:
        constant = type(exponent) is int or type(exponent) is bool
        if modulus is None and constant and 0 <= cast(int, exponent) < _POWER_LIMIT:
            expression = ["**", self.expression, cast(int, exponent)]
            return tracked(own(operation, self, exponent), expression, self.sink)
        return downgrade(self, exponent, modulus)

    return compute


def rounded(whole: Callable[[Any], object]) -> Callable[..., Any]:
    """Rounding a whole number to zero or more digits is `whole` of it; to tens, a downgrade.

    `whole` is what the type answers for the number it already is: an int
    hands itself back, a bool the int 1 or 0. A plain bool counts digits as
    the int 1 or 0 it is, as it does for an exponent.
    """
    downgrade = downgraded(int, "__round__")

    def compute(self: Number, ndigits: object = None) -> Any:
        digits = type(ndigits) is int or type(ndigits) is bool
        if ndigits is None or (digits and cast(int, ndigits) >= 0):
            return whole(self)
        return downgrade(self, ndigits)

    return compute


def itself(operation: Callable[..., object], whole: Callable[[Any], object]) -> Callable[..., Any]:
    """A method whose answer is the value itself, as `whole` hands it back, so no node is added.

    `whole` is what the type answers for the number it already is: an int
    or a float hands itself back, a bool the int 1 or 0. The base type's own
    method runs first on the arguments as the target wrote them, so a call it
    refuses raises its own error, and its plain answer, the same number, is
    dropped.
    """

    def compute(self: Number, /, *args: object, **kwargs: object) -> Any:
        own(operation, self, *args, **kwargs)
        return whole(self)

    return compute


def ratio(whole: Callable[[Any], object]) -> Callable[..., Any]:
    """An int's `as_integer_ratio`: the value itself, as `whole` hands it back, over int's own 1."""

    def compute(self: Number, /, *args: object, **kwargs: object) -> Any:
        _, denominator = own(int.as_integer_ratio, self, *args, **kwargs)
        return whole(self), denominator

    return compute


def attribute(descriptor: Any, whole: Callable[[Any], object]) -> property:
    """An attribute whose value is the number itself, as `whole` hands it back.

    `descriptor` is the base type's own, such as `int.real`. Setting or
    deleting the attribute goes to it, so it raises the AttributeError
    Python raises on a plain value, naming the base type.
    """

    def write(self: Number, value: object) -> None:
        own(descriptor.__set__, self, value)

    def remove(self: Number) -> None:
        own(descriptor.__delete__, self)

    return property(whole, write, remove)
