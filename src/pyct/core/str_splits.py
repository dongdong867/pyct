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


def _separator(receiver: object, value: object) -> Expression | None:
    """A separator pyct encodes: None, for whitespace, or a plain str.

    The expression holds None, which the line prints as ``null``. An empty
    str is Python's own ValueError, raised before a piece is built.
    """
    return None if value is None else literal(value, type(receiver))


def separator_and_limit(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """What a split pyct encodes was called with: nothing, a separator, and a plain int limit."""
    if len(args) > 2:
        return None
    operands: list[Expression] = []
    if args:
        written = _separator(receiver, args[0])
        if args[0] is not None and written is None:
            return None
        operands.append(written)
    if len(args) == 2:
        if (limit := position(args[1])) is None:
            return None
        operands.append(limit)
    return operands


def _overlaps_itself(separator: str) -> bool:
    """Whether a separator's start can be its own end: ``aa``, ``aba``."""
    return any(separator[:size] == separator[-size:] for size in range(1, len(separator)))


def from_the_right(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """What an rsplit pyct encodes was called with, as a split's.

    With no limit, the solver reads an rsplit as the split it matches, which
    it is unless its separator overlaps itself: ``"aaa".rsplit("aa")`` is
    ``["a", ""]`` where ``split`` finds ``["", "a"]``.
    """
    operands = separator_and_limit(receiver, args)
    limit = position(args[1]) if len(args) == 2 else None
    separator = args[0] if args else None
    unlimited = limit is None or limit < 0
    if unlimited and isinstance(separator, str) and _overlaps_itself(separator):
        return None
    return operands


def one_separator(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """partition's one operand, a plain str."""
    if len(args) != 1 or args[0] is None:
        return None
    written = _separator(receiver, args[0])
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
