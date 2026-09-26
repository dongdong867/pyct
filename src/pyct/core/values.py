"""What every concolic type shares.

The call into the base type, the fork a truth test records, and the
downgrades derived for what a type has not taught.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from typing import Protocol

from pyct.core.branch import Branch, BranchSink, Downgrade, Expression, caller_site

# the mark that says a raise came out of the base type's own operation. The call that made it
# is the only code that knows, so it writes the mark there and blame reads it back
_TARGET_RAISE = "__pyct_target_raise__"


def own[T](operation: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    """The base type's own answer, with a raise out of it marked as the target's.

    Every call pyct makes into the base type goes through here, taught
    operation and downgrade alike. A raise under one of them is the target's
    program failing, not a pyct bug. Only an ``Exception`` is one: a deadline
    and a keyboard interrupt land here too, and neither is the operation's.
    """
    try:
        return operation(*args, **kwargs)
    except Exception as error:
        setattr(error, _TARGET_RAISE, True)
        raise


def raised_by_target(error: BaseException) -> bool:
    """Whether this raise came out of the base type's own operation."""
    return getattr(error, _TARGET_RAISE, False) is True


def forked(sink: BranchSink, expression: Expression, taken: bool) -> bool:
    """Record the fork a truth test just took, and answer with the side it took.

    Python demands a real bool back from ``__bool__``, so no concolic type can
    answer with a value that carries the condition; the condition goes to the
    sink here instead. One helper, so every type records it the same way.
    """
    sink.append(Branch(expression=expression, taken=taken, site=caller_site()))
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


class _Sinked(Protocol):
    """A value with a sink: all a downgrade needs of the type it is set on."""

    sink: BranchSink


def downgraded(base: type, name: str) -> Callable[..., object]:
    """The base type's own operation, and a note in the sink that the condition was lost.

    The arguments reach the base type's operation as the target wrote them,
    keywords too, so the operation takes and refuses what it would take and
    refuse on a plain value. The note comes after the call, so an operation
    that raises records nothing and the raise stays the target's.
    ``NotImplemented`` is not an answer either: the other operand's reflected
    method gets its turn, and only a real result is a lost condition.
    """
    operation = getattr(base, name)

    def downgrade(self: _Sinked, /, *args: object, **kwargs: object) -> object:
        result = own(operation, self, *args, **kwargs)
        if result is not NotImplemented:
            self.sink.append(Downgrade(name=name))
        return result

    return downgrade


def _called_on_a_value(member: object) -> bool:
    """Whether a name a type defines is a method called on a value of it."""
    return isinstance(
        member, types.FunctionType | types.WrapperDescriptorType | types.MethodDescriptorType
    )


def downgrade_the_rest(
    cls: type, base: type, *, kept: tuple[str, ...], inherited: tuple[str, ...]
) -> None:
    """Downgrade every method of the base type the concolic type has not taught.

    A type teaches what its class body defines and names what it keeps as
    the base type's; every other method the base type defines is a
    downgrade, worked out here once the class is built. Only a method
    called on a value counts: a classmethod, a staticmethod, an attribute
    and the rest never take a tracked value as their receiver, so none of
    them can lose a condition. A name the base type inherits is reached
    only by naming it, and a kept name the base type does not define is
    simply not there to wrap.
    """
    candidates = {name for name, member in vars(base).items() if _called_on_a_value(member)}
    candidates |= set(inherited)
    for name in sorted(candidates - set(vars(cls)) - set(kept)):
        setattr(cls, name, downgraded(base, name))
