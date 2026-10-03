"""What every concolic type shares.

The call into the base type, the fork a truth test records, and the
downgrades derived for what a type has not taught.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any, Protocol

from pyct.core.branch import Branch, BranchSink, Downgrade, Expression, caller_site, lost_at

# the mark that says a raise came out of a call pyct made for the target. The call that made it
# is the only code that knows, so it writes the mark there and blame reads it back
_TARGET_RAISE = "__pyct_target_raise__"


def own[T](operation: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    """The answer of a call pyct makes for the target, a raise out of it marked as the target's.

    Every call pyct makes into the base type goes through here, taught
    operation and downgrade alike, and so do the reads and compiles of the
    target's own files that pyct makes in Python's place as it imports them.
    A raise under one of them is the target's program failing, not a pyct
    bug. Only an ``Exception`` is one: a deadline and a keyboard interrupt
    land here too, and neither is the operation's.
    """
    try:
        return operation(*args, **kwargs)
    except Exception as error:
        setattr(error, _TARGET_RAISE, True)
        raise


def raised_by_target(error: BaseException) -> bool:
    """Whether this raise came out of a call pyct made for the target, through `own`."""
    return getattr(error, _TARGET_RAISE, False) is True


# set while pyct tests a value for truth on its way into an operation that may raise, so the
# fork that test records is marked as that operation's
_BEFORE_A_RAISE = [False]


def forked(
    sink: BranchSink,
    expression: Expression,
    taken: bool,
    name: str = "__bool__",
    *,
    raising: bool = False,
) -> bool:
    """Record the fork a truth test just took, and answer with the side it took.

    Python demands a real bool back from ``__bool__``, so no concolic type can
    answer with a value that carries the condition; the condition goes to the
    sink here instead. One helper, so every type records it the same way.
    ``name`` is the operation that took it: a truth test, or a list's walk or index.
    ``raising`` marks a fork taken before an operation that may raise.
    """
    marked = raising or _BEFORE_A_RAISE[0]
    branch = Branch(expression, taken, caller_site(), raising=marked, lost_as=name)
    sink.append(branch)
    return taken


def walked_a_split(sink: BranchSink, expression: Expression, taken: bool, name: str) -> bool:
    """Record a walk's fork over a split's list as ``forked`` records a fork, marked so the
    tree aims at it after the path's other forks
    (fork-order-a-split-s-walk-forks-after-the-path-s-other-forks)."""
    site, marked = caller_site(), _BEFORE_A_RAISE[0]
    sink.append(Branch(expression, taken, site, raising=marked, lost_as=name, split_walk=True))
    return taken


def before_a_raise(test: Callable[[], object]) -> None:
    """Run ``test``, whose truth test is the fork an operation takes before it may raise.

    The truth test goes through each type's own ``__bool__``, which records
    the fork as any truth test does; this marks it as the operation's.
    """
    try:
        _BEFORE_A_RAISE[0] = True
        test()
    finally:
        _BEFORE_A_RAISE[0] = False


def copy_as_itself[T](value: T, memo: object = None) -> T:
    """A copy of a concolic value, shallow or deep: the value itself.

    A concolic value cannot change, so copy hands it back as it is, the way
    it hands back a plain str or int, with its expression and sink on it.
    Set as ``__copy__`` and ``__deepcopy__``, which the copy module asks for
    before it would rebuild the value through ``__new__`` without them. The
    memo is what ``__deepcopy__`` is given, and nothing here needs it.
    """
    return value


def plain(value: object, kind: type) -> object:
    """The value as Python's own ``kind`` holds it: the same text or number, with no condition.

    ``kind``'s own ``__getnewargs__`` answers what the value is rebuilt from,
    as pickle rebuilds a subclass of it, and reads the value without calling
    any method a concolic type overrides, so nothing is recorded. ``kind``
    then builds its own value from that, so a compare's answer, which int
    reads as 1 or 0, comes back a bool.
    """
    return kind(*kind.__getnewargs__(value))


class _Sinked(Protocol):
    """A value with a sink: all a downgrade needs of the type it is set on."""

    sink: BranchSink


# what a type may answer before its base type's own operation, given the operation's name, the
# tracked value, the other operand and any modulus: an answer, or NotImplemented to go on to the
# base type's. Its arguments are left unchecked because a Protocol taking the modulus would make
# `texts.alone`, which answers `__format__` and never meets one, take a parameter it never uses
type First = Callable[..., object]


class _ReflectedPower(int):
    """An int whose own reflected power answers: what pyct asks the running Python about."""

    def __rpow__(self, other: object, modulus: object = None) -> object:  # pyrefly: ignore[bad-override]
        return _ReflectedPower


# whether Python asks the right operand's reflected power for a three-argument pow, as it does
# for two: from 3.14. Asked of the running Python, not read from its version
_ASKED_WITH_A_MODULUS = pow(0, _ReflectedPower(), 1) is _ReflectedPower


def asked_of_the_right_first(name: str, args: tuple[object, ...]) -> bool:
    """Whether Python asks the right operand before the left one's operation with these arguments.

    It does for a call on one operand, and for a power with a modulus on a
    Python that asks for it (`_ASKED_WITH_A_MODULUS`); ``first`` and the
    type's own rule then say whether the right operand is one it asks.
    """
    return len(args) == 1 or (len(args) == 2 and name == "__pow__" and _ASKED_WITH_A_MODULUS)


def downgraded(
    base: type,
    name: str,
    *,
    calling: Callable[..., object] | None = None,
    first: First | None = None,
) -> Callable[..., object]:
    """The base type's own operation, and a note in the sink that the condition was lost.

    The arguments reach the operation as the target wrote them, keywords
    too, so it takes and refuses what it would take and refuse on a plain
    value. The note comes after the call, so an operation that raises
    records nothing and the raise stays the target's. ``NotImplemented`` is
    not an answer either: the other operand's reflected method gets its
    turn, and only a real result is a lost condition. A result that is the
    receiver itself, as str's `%`, `format` and `__format__` can give, comes
    back as the receiver's plain value.

    ``calling`` is how the base type answers when its method by that name
    is not the answer: str has no `__radd__`, and its reflected
    concatenation is its `__add__` the other way round; a tracked bool
    formats as the bool it is, where int's `__format__` writes a number; and
    a split runs on plain values, so that none of its pieces is tracked.
    Such a replacement may turn its arguments into plain values, and it is
    what takes and refuses them. The downgrade is still named ``name``.
    ``first`` answers a call Python asks the right operand for first
    (`asked_of_the_right_first`) before the base type does, when it has an
    answer, and that answer comes back as it is: ``first`` names any
    downgrade it makes.
    """
    operation = getattr(base, name) if calling is None else calling

    def downgrade(self: _Sinked, /, *args: object, **kwargs: object) -> object:
        if first is not None and not kwargs and asked_of_the_right_first(name, args):
            answer = first(name, self, *args)
            if answer is not NotImplemented:
                return answer
        result = own(operation, self, *args, **kwargs)
        if result is NotImplemented:
            return result
        # the call's own caller is where the walk for the site starts
        self.sink.append(lost_at(name, sys._getframe(1)))
        return own(plain, self, base) if result is self else result

    return downgrade


# what pickle is handed for a value: the type that rebuilds it, and what that type is called with
type Pickled = tuple[type, tuple[object]]


def pickled(kind: type) -> tuple[Callable[..., Pickled], Callable[..., Pickled]]:
    """A tracked value's ``__reduce_ex__`` and ``__reduce__``: its plain value, loading as ``kind``.

    pickle asks a tracked value for ``__reduce_ex__`` at every protocol, so
    no pickle rebuilds a concolic type, whose class called with a value
    builds a plain one, and no pickle holds the sink. A pickle can load in
    another process or a later input, where the condition does not apply, so
    writing one is a downgrade named by the method Python called, and the
    value that was pickled keeps its condition (pickle-holds-the-plain-value).
    Each takes the arguments Python's own does: one protocol, and none. The
    copy module asks for ``__copy__`` and ``__deepcopy__`` first, so a copy
    stays the value itself.
    """

    def reduce_ex(self: _Sinked, protocol: int, /) -> Pickled:
        # every protocol writes the same
        return _written(self, own(plain, self, kind), "__reduce_ex__")

    def reduce(self: _Sinked, /) -> Pickled:
        return _written(self, own(plain, self, kind), "__reduce__")

    return reduce_ex, reduce


def _written(value: _Sinked, held: object, name: str) -> Pickled:
    """Record writing a pickle as a downgrade, and answer with its plain value and type."""
    value.sink.append(Downgrade(name=name, site=caller_site()))
    return type(held), (held,)


# each tracked class and the base type Python's own value has: the one table of them, its rows
# written by `pyct.core.bases` once every tracked class exists. A tracked value reports its row
# as its class, and its class called outside pyct's construction builds that type's value
BASES: dict[type, type] = {}
# the same rows by the tracked class's identity, and each dict view's Python type, for code
# that meets any class, as the `type` router does: reading a class's identity runs none of its
# code, where hashing it may
BASES_BY_ID: dict[int, type] = {}

# what each base type is called with for a plain value of its own, when not with nothing
_EMPTY: dict[type, tuple[object, ...]] = {range: (0,)}


def named_as(cls: type, base: type) -> None:
    """Give a class of pyct's the name, qualified name and module of a type Python has.

    Python writes a value's type into a message from its real class, which
    ``__class__`` does not reach, as in `'int' object is not subscriptable`,
    and from 3.14 some messages with the module and qualified name as well.
    So a message on a tracked value names what it names on a plain one
    (tracked-classes-carry-their-base-type-s-names). pyct tells its classes
    apart by identity, never by name.
    """
    cls.__name__ = base.__name__
    cls.__qualname__ = base.__qualname__
    cls.__module__ = base.__module__


def base_value(kind: type) -> object:
    """A plain value of a base type, as Python's own ``kind`` builds one: from nothing, or from
    0 for a range. What Python says of it names its type in Python's words."""
    return kind(*_EMPTY.get(kind, ()))


def _base_class(self: object) -> type:
    """The class a tracked value reports: its base type, as Python's own value reads it."""
    return BASES[type(self)]


def _assigned_class(self: object, kind: object) -> None:
    """`object.__setattr__(v, "__class__", kind)`: made on a plain value of the base type, so
    Python raises its own error, in its words. `v.__class__ = kind` never gets here: each
    tracked class's `refused_set` makes it on the plain value first, with the same answer.
    """
    own(setattr, base_value(BASES[type(self)]), "__class__", kind)


def refused_set(self: object, name: str, value: object, /) -> None:
    """`v.name = value` on a tracked value: made on a plain value of its base type instead.

    A plain int, bool, float, str, list, dict or range takes no attribute of
    its own, so Python raises its own error, in the running release's words,
    and the target's handler sees what it would see. The names pyct keeps on
    the value are refused too, since the plain value has none of them; pyct
    writes them past this, into the value's `__dict__`, or its slots for a
    range. Setting an attribute is object plumbing, so nothing is recorded
    (tracked-numbers-refuse-attributes-on-a-plain-number).
    """
    own(setattr, base_value(BASES[type(self)]), name, value)


def refused_delete(self: object, name: str, /) -> None:
    """`del v.name` on a tracked value: made on a plain value of its base type, as a set is."""
    own(delattr, base_value(BASES[type(self)]), name)


# a tracked class's `__class__`: its base type. `isinstance` and `issubclass` fall back to it
# when the real type does not match, and `functools.singledispatch` and a class pattern read it,
# so each answers as for the plain value (tracked-values-report-their-base-type-as-their-class).
# It reads the class and never the value, so it records nothing. `type(v)` still reads the real
# class, which is how pyct tells a tracked value apart
REPORTED_CLASS = property(_base_class, _assigned_class)


def as_base(cls: type, /, *args: object, **kwargs: object) -> Any:
    """A tracked class called outside pyct's construction: its base type's own plain value.

    Code that calls the class a value reports, as `type(v)(5)` does outside
    the target's package, gets what the base type builds from the same
    arguments, or its raise.
    """
    return own(BASES[cls], *args, **kwargs)


def built_plainly(kind: type, name: str) -> Any:
    """A classmethod of ``kind`` reached through a tracked value: ``kind``'s own answer, plain.

    ``kind``'s own classmethod builds the class it is reached through from
    the value alone, and a concolic class also needs an expression and a
    sink, so it is asked of ``kind`` itself: `x.from_bytes(...)` and
    `type(x).from_bytes(...)` answer as `int.from_bytes(...)` does. It reads
    the class and never the value, so it records nothing
    (downgrades-class-body-taught-attributes-named).
    """
    operation = getattr(kind, name)

    def build(cls: type, /, *args: object, **kwargs: object) -> object:
        return own(operation, *args, **kwargs)

    return classmethod(build)


def converted(kind: type, name: str) -> Any:
    """A classmethod of ``kind`` that converts one value to ``kind``, reached through a tracked
    value.

    A tracked value of the class it is reached through is already the value
    it would build, so it comes back as it is, as `float(f)` is `f`
    (`pyct.core.conversions`). Anything else gets ``kind``'s own answer,
    plain, as `built_plainly` gives it; a tracked number of another type is
    read through its own conversion, which names what it loses.
    """
    operation = getattr(kind, name)

    def convert(cls: type, /, *args: object, **kwargs: object) -> object:
        if len(args) == 1 and not kwargs and type(args[0]) is cls:
            return args[0]
        return own(operation, *args, **kwargs)

    return classmethod(convert)


def _called_on_a_value(member: object) -> bool:
    """Whether a name a type defines is a method called on a value of it."""
    return isinstance(
        member, types.FunctionType | types.WrapperDescriptorType | types.MethodDescriptorType
    )


def downgrade_the_rest(
    cls: type,
    base: type,
    *,
    kept: tuple[str, ...],
    inherited: tuple[str, ...],
    first: First | None = None,
) -> None:
    """Downgrade every method of the base type the concolic type has not taught.

    A type teaches what its class body defines and names what it keeps as
    the base type's; every other method the base type defines is a
    downgrade, worked out here once the class is built. Only a method
    called on a value counts: an attribute that reads the value and a
    classmethod are named in the type's class body instead, and a
    staticmethod never takes a tracked value as its receiver
    (downgrades-class-body-taught-attributes-named). A name the base type
    inherits is reached only by naming it, and a kept name the base type
    does not define is simply not there to wrap. ``first`` is handed to
    each downgrade (see `downgraded`).
    """
    candidates = {name for name, member in vars(base).items() if _called_on_a_value(member)}
    candidates |= set(inherited)
    for name in sorted(candidates - set(vars(cls)) - set(kept)):
        setattr(cls, name, downgraded(base, name, first=first))


def held_by(operation: Callable[..., object]) -> Callable[..., object]:
    """A base type's operation, called on the base type's own value a stand-in holds.

    A stand-in is a concolic type Python does not let extend its base type,
    as `range` refuses a subclass. It holds the base type's value as
    ``held``, and the base type's method answers on that.
    """

    def call(self: Any, /, *args: object, **kwargs: object) -> object:
        return operation(self.held, *args, **kwargs)

    return call


def downgrade_through(cls: type, base: type, *, kept: tuple[str, ...]) -> None:
    """Downgrade every method of the base type a stand-in has not taught, on the value it holds.

    As `downgrade_the_rest` derives them for a subclass, but each calls the
    base type's own method on ``held`` (see `held_by`) and records the loss.
    """
    candidates = {name for name, member in vars(base).items() if _called_on_a_value(member)}
    for name in sorted(candidates - set(vars(cls)) - set(kept)):
        setattr(cls, name, downgraded(base, name, calling=held_by(getattr(base, name))))
