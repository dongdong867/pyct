"""What a tracked str teaches about its characters: the checks, the case changes, the strips and
the paddings.

Each answers with str's own value, carrying ``[name, s, *operands]``: a
check as a tracked bool, the rest as a tracked str of the receiver's own
type. A call in a form pyct does not encode, a keyword included, is str's
own answer and a downgrade named by the method (``README.md › Rules ›
downgrades``). The forms pyct encodes take their operands plain: a width
is a plain int, and the characters a strip removes or a padding fills with
are a plain str the solver holds. A tracked one is a downgrade.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Expression
from pyct.core.str_operands import literal, position
from pyct.core.values import downgraded, own

# how a method reads its arguments: the operands pyct encodes, or None for a form it does not
type Reader = Callable[[object, tuple[object, ...]], list[Expression] | None]


class Tracked(Protocol):
    """What a method here needs of the tracked str it is called on."""

    expression: Expression
    sink: BranchSink


def _nothing(_receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """A method that takes no argument: no operand, and any argument is a form not encoded."""
    return None if args else []


def characters(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """The characters a strip removes: none, None for whitespace, or a plain str."""
    if not args or (len(args) == 1 and args[0] is None):
        return []
    if len(args) != 1 or (written := literal(args[0], type(receiver))) is None:
        return None
    return [written]


def width_and_fill(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """A padding's width, a plain int, and the character it fills with, a plain str."""
    if not args or len(args) > 2 or (columns := position(args[0])) is None:
        return None
    if len(args) == 1:
        return [columns]
    written = literal(args[1], type(receiver))
    return None if written is None else [columns, written]


def width(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """zfill's one operand, a plain int width."""
    return width_and_fill(receiver, args) if len(args) == 1 else None


def piece(receiver: Tracked, value: str, expression: Expression) -> object:
    """A str the receiver built, tracked as the receiver's own type is, carrying ``expression``."""
    made: Callable[..., object] = type(receiver).made  # pyrefly: ignore[missing-attribute]
    return made(value, expression, receiver.sink)


def check(name: str) -> Callable[..., object]:
    """str's own answer to one character check, as a tracked bool carrying ``[name, s]``."""
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: Tracked, /, *args: object, **kwargs: object) -> object:
        if args or kwargs:
            return downgrade(self, *args, **kwargs)
        value = own(operation, self)
        return ConcolicBool.made(value, expression=[name, self.expression], sink=self.sink)

    return compute


def changed(name: str, reader: Reader = _nothing) -> Callable[..., object]:
    """str's own answer to one method that builds a str from s, as a tracked str carrying
    ``[name, s, *operands]``, the operands as ``reader`` finds them: a case change, a strip or
    a padding here, and replace and the removals in strs."""
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: Tracked, /, *args: object, **kwargs: object) -> object:
        forms = None if kwargs else reader(self, args)
        if forms is None:
            return downgrade(self, *args, **kwargs)
        return piece(self, own(operation, self, *args), [name, self.expression, *forms])

    return compute
