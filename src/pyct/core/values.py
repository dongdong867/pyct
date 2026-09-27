"""What every concolic type shares.

The call into the base type, the fork a truth test records, and the
downgrades derived for what a type has not taught.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from typing import Any, Protocol

from pyct.core.branch import Branch, BranchSink, Downgrade, Expression, caller_site

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


def forked(
    sink: BranchSink,
    expression: Expression,
    taken: bool,
    name: str = "__bool__",
    holds: Expression = None,
) -> bool:
    """Record the fork a truth test just took, and answer with the side it took.

    Python demands a real bool back from ``__bool__``, so no concolic type can
    answer with a value that carries the condition; the condition goes to the
    sink here instead. One helper, so every type records it the same way.
    ``name`` is the operation that took it: a truth test, or a list's walk or index.
    ``holds`` is what the input keeps once the fork went this way (see ``Branch``).
    """
    site = caller_site()
    sink.append(Branch(expression=expression, taken=taken, site=site, lost_as=name, holds=holds))
    return taken


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
# tracked value and the one argument: an answer, or NotImplemented to go on to the base type's
type First = Callable[[str, object, object], object]


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
    ``first`` answers a call on one argument before the base type does,
    when it has an answer, and that answer comes back as it is: ``first``
    names any downgrade it makes.
    """
    operation = getattr(base, name) if calling is None else calling

    def downgrade(self: _Sinked, /, *args: object, **kwargs: object) -> object:
        if first is not None and len(args) == 1 and not kwargs:
            answer = first(name, self, args[0])
            if answer is not NotImplemented:
                return answer
        result = own(operation, self, *args, **kwargs)
        if result is NotImplemented:
            return result
        self.sink.append(Downgrade(name=name))
        return own(plain, self, base) if result is self else result

    return downgrade


# what pickle is handed for a value: the type that rebuilds it, and what that type is called with
type Pickled = tuple[type, tuple[object]]


def pickled(kind: type) -> tuple[Callable[..., Pickled], Callable[..., Pickled]]:
    """A tracked value's ``__reduce_ex__`` and ``__reduce__``: its plain value, loading as ``kind``.

    pickle asks a tracked value for ``__reduce_ex__`` at every protocol, so
    no pickle rebuilds a concolic type through a ``__new__`` that needs an
    expression and a sink, and no pickle holds the sink. A pickle can load in
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
    value.sink.append(Downgrade(name=name))
    return type(held), (held,)


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
