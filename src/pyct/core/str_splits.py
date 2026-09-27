"""What a tracked str teaches about splitting: split, rsplit, partition and splitlines.

Each hands back what str's own method does, a list, or a tuple for
``partition``, with every piece a tracked str carrying
``["[]", [name, s, *operands], k]``, k its position in what Python built. The
list itself is plain: Python indexes it, and ``len(parts)`` is plain. A call
in a form pyct does not encode, a keyword included, is str's own answer and a
downgrade named by the method (``README.md › Rules › downgrades``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from pyct.core.branch import Expression
from pyct.core.str_cases import Reader, Tracked, piece
from pyct.core.str_operands import literal, plain, position
from pyct.core.values import downgraded, own


def _parsed(
    receiver: object, args: tuple[object, ...]
) -> tuple[list[Expression], str | None, int] | None:
    """A split pyct encodes, read once: its operands as the call wrote them, the separator's
    text, None for whitespace, and the limit, -1 for none. Any other form is None.

    A separator is None or a plain str the solver holds, so nothing here
    runs a method of a tracked one. The expression holds None, which the
    line prints as ``null``. An empty separator is Python's own ValueError,
    raised before a piece is built.
    """
    if len(args) > 2:
        return None
    separator = args[0] if args else None
    written = None if separator is None else literal(separator, type(receiver))
    if separator is not None and written is None:
        return None
    limit = position(args[1]) if len(args) == 2 else -1
    if limit is None:
        return None
    text = None if separator is None else plain(separator)
    operands: list[Expression] = [written, limit]
    return operands[: len(args)], text, limit


def separator_and_limit(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """What a split pyct encodes was called with: nothing, a separator, and a plain int limit."""
    parsed = _parsed(receiver, args)
    return None if parsed is None else parsed[0]


def _overlaps_itself(separator: str) -> bool:
    """Whether a separator's start can be its own end: ``aa``, ``aba``."""
    return any(separator[:size] == separator[-size:] for size in range(1, len(separator)))


def from_the_right(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """What an rsplit pyct encodes was called with, as a split's.

    With no limit, the solver reads an rsplit as the split it matches, which
    it is unless its separator overlaps itself: ``"aaa".rsplit("aa")`` is
    ``["a", ""]`` where ``split`` finds ``["", "a"]``. The check reads the
    plain separator, so it records nothing on the target's line.
    """
    parsed = _parsed(receiver, args)
    if parsed is None:
        return None
    operands, text, limit = parsed
    return None if limit < 0 and text is not None and _overlaps_itself(text) else operands


def one_separator(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """partition's one operand, a plain str."""
    if len(args) != 1:
        return None
    written = literal(args[0], type(receiver))
    return None if written is None else [written]


def line_ends(_receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """splitlines' one operand, whether it keeps the line ends: none, or a plain int or bool."""
    if not args:
        return []
    kept = position(args[0]) if len(args) == 1 else None
    return None if kept is None else [bool(kept)]


def split_up(name: str, reader: Reader) -> Callable[..., object]:
    """str's own split, each piece a tracked str at its position in what Python built."""
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: Tracked, /, *args: object, **kwargs: object) -> object:
        forms = None if kwargs else reader(self, args)
        if forms is None:
            return downgrade(self, *args, **kwargs)
        # str's own split on the plain value: on a subclass, partition and rsplit may ask for
        # its text through `__str__`, which pyct's call is not the target's downgrade
        parts = own(operation, plain(self), *args)
        pieces = _pieces(self, [name, self.expression, *forms], parts)
        return tuple(pieces) if isinstance(parts, tuple) else list(pieces)

    return compute


def _pieces(receiver: Tracked, whole: Expression, parts: Iterable[str]) -> Iterable[object]:
    """Each piece of what Python built, tracked, carrying ``["[]", whole, k]``.

    Every piece holds the one ``whole``, so a program reads the split once.
    """
    return (piece(receiver, part, ["[]", whole, at]) for at, part in enumerate(parts))
