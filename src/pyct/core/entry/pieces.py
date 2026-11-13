"""The hooks around each piece of the target's functions: a loop, and an assignment of a
comprehension (`pyct.results.pieces`).

With the interception's pieces switch on, `pyct.intercept.loops` writes a
call of these functions where each piece starts and where it ends, through
a name it binds in the module, such as ``__pyct_piece_over__``. Each call
is given the piece's site and names as constants, in this order: its line,
its column, the names going in and the changed names, each a tuple of
str. The file is the one the caller's code names. Each hook is called from
the target's own frame, so ``sys._getframe(1)`` is the piece's frame.

For now each hook hands back what the target's code needs, and records
nothing.
"""

from __future__ import annotations


def piece_over[Iterated](
    iterable: Iterated, line: int, col: int, going_in: tuple[str, ...], changed: tuple[str, ...], /
) -> Iterated:
    """A ``for`` or ``async for`` starts: called once per run of the loop, with the iterable it
    was written with, after the iterable is evaluated and before Python asks it for an
    iterator. It hands back what the loop iterates over, the iterable itself."""
    return iterable


def piece_in(line: int, col: int, going_in: tuple[str, ...], changed: tuple[str, ...], /) -> object:
    """A ``while`` or an assignment of a comprehension starts: called once per run, a
    ``while``'s before its test is first evaluated, an assignment's before its value is. It hands
    back a token, which an assignment hands to `piece_value` and a ``while`` drops."""
    return None


def piece_out(line: int, col: int, going_in: tuple[str, ...], changed: tuple[str, ...], /) -> None:
    """A loop's run ends, by exhaustion, by its test going false or by a ``break`` that leaves it:
    called once per run, after its last pass and before its ``else`` runs, or right before the
    ``break``. A run that ends by ``return`` or a raise calls it not at all, and a ``while True``
    only at a ``break``. It hands back None, which the caller drops."""


def piece_value[Value](token: object, value: Value, /) -> Value:
    """An assignment of a comprehension ends: called once per run, with the token `piece_in` gave
    for this run and the value, before it is stored into the target, which is the piece's one
    changed name. It hands back the value to store."""
    return value
