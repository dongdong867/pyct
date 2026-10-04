"""What a tracked str teaches about splitting: split, rsplit, partition and splitlines.

``split``, ``rsplit`` and ``splitlines`` hand back a tracked list whose form is the call,
``[name, s, *operands]``, the operands by position: a keyword goes to its place, so
``s.split(maxsplit=1)`` is ``["split", s, None, 1]``. Its length is followed as any tracked
list's, and every piece is a tracked str carrying ``["[]", [name, s, *operands], k]``, k its
position in what Python built. ``partition`` hands back str's own tuple of such pieces. A call
in a form pyct does not encode is str's own answer and a downgrade named by the method
(``README.md › Rules › downgrades``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from pyct.core.branch import BranchSink, Expression
from pyct.core.str_cases import Reader, Tracked, piece
from pyct.core.str_operands import literal, plain, position
from pyct.core.values import downgraded, own

# the largest rsplit limit the solver walks one separator or word at a time. On cvc5 1.3.4 a
# flipped piece solved in 0.5 to 1.5 s at 16, 2.3 to 6.2 s at 32, and ran past the 10 s limit
# at 64. Past it, the solver reads an rsplit as the split with no limit, which it is on a string
# with no more separators than the limit, or fewer words (see `solver/splits.py`)
LONGEST_WALK = 16

# the splits that hand back a tracked list; `partition` hands back a tuple of three
LISTED_SPLITS = frozenset({"split", "rsplit", "splitlines"})

# the heads that build a list from the lists among their operands; a display or a read of an
# item builds none, so a piece it holds makes no list of it a split's
_BUILT_FROM = frozenset({"+", "*", "[:]"})


def splits_built_from(form: object) -> list[list[object]]:
    """The splits' lists a list's form is, or is built from by ``+``, ``*`` or a slice. A list
    changed in place names the list before it more than once, so each part is looked at once.
    """
    found: list[list[object]] = []
    stack, seen = [form], set()
    while stack:
        part = stack.pop()
        if not isinstance(part, list) or not part or not isinstance(part[0], str):
            continue
        if id(part) in seen:
            continue
        seen.add(id(part))
        if part[0] in LISTED_SPLITS:
            found.append(part)
        elif part[0] in _BUILT_FROM:
            stack.extend(part[1:2] if part[0] == "[:]" else part[1:])
    return found


def built_from_a_split(form: object) -> bool:
    """Whether a list's form is a split's list, or a list built from one."""
    return bool(splits_built_from(form))


# how deep a split's list's form, or the form of the string a split splits, may nest and still
# be one the solver writes exactly
_DEEPEST = 64

# the str methods whose answer the solver works out from the input's string, each called with
# plain operands
WORKED_METHODS = frozenset(
    {
        *("lower", "upper", "casefold", "swapcase", "title", "capitalize"),
        *("strip", "lstrip", "rstrip", "removeprefix", "removesuffix", "replace"),
        *("center", "ljust", "rjust", "zfill", "expandtabs"),
    }
)


def a_split_s_list(form: object, depth: int = _DEEPEST) -> bool:
    """Whether a list's form is a split's list the solver writes exactly: a cut of one
    (``_cut``), or one with a list display joined on either side, nested at most ``depth``
    deep."""
    if not isinstance(form, list) or not form or depth == 0:
        return False
    if form[0] == "+" and len(form) == 3:
        shown = [part for part in form[1:] if isinstance(part, list) and part[:1] == ["[,]"]]
        others = [part for part in form[1:] if part not in shown]
        return len(others) == 1 and a_split_s_list(others[0], depth - 1)
    return _cut(form, depth)


def _cut(form: object, depth: int) -> bool:
    """Whether a list's form is a split's list, or a slice of one with plain bounds and a step
    of 1 or -1, or a slice so of such a slice that starts from its start or steps back from its
    end: the solver writes a slice of a slice only with such a start."""
    if not isinstance(form, list) or not form or depth == 0:
        return False
    head, operands = form[0], form[1:]
    if head in LISTED_SPLITS:
        return True
    if head != "[:]" or not _plain_bounds(operands[1:]) or operands[3:] not in _STEPS:
        return False
    inner, start, step = operands[0], operands[1], (*operands[3:], None)[0]
    from_its_start = step != -1 and (start is None or start >= 0)
    stepped_back = step == -1 and start is None
    if isinstance(inner, list) and inner[:1] == ["[:]"] and not (from_its_start or stepped_back):
        return False
    return _cut(inner, depth - 1)


# the steps of a slice the solver writes exactly: none, 1 or -1
_STEPS = ([], [None], [1], [-1])


def _plain_bounds(bounds: list[Expression]) -> bool:
    return all(bound is None or type(bound) is int for bound in bounds)


def kept_form(form: Expression) -> Expression:
    """A list's form, or None where a split's list was changed into one the solver does not
    write exactly, which then leaves the split's machinery for Python's own list, as origin/v2
    hands it back: its pieces stay tracked and the list records nothing."""
    return None if built_from_a_split(form) and not a_split_s_list(form) else form


def worked_out(form: Expression, depth: int = _DEEPEST) -> bool:
    """Whether the solver works out the value a string's form has in the input from the input's
    own values: a str argument or a literal, or a slice with plain bounds, a join, a repeat by
    a plain int, a `WORKED_METHODS` call with plain operands, or an index by a plain int into
    a string or a split's list that one of those calls made (`_made_by_a_call`), of parts worked
    out so. Only what a call made is indexed: an argument indexed may be a list's item, whose
    value the solver does not hold."""
    if not isinstance(form, list):
        return isinstance(form, str)
    if not form or depth == 0:
        return False
    head, operands = form[0], form[1:]
    if head == "+" and len(operands) == 2:
        return all(worked_out(part, depth - 1) for part in operands)
    if head == "[]" and not _made_by_a_call(operands[0], depth - 1):
        return False
    if head in ("[:]", "[]", "*") and _plain_bounds(operands[1:]):
        return worked_out(operands[0], depth - 1)
    if head in WORKED_METHODS or head in LISTED_SPLITS:
        return worked_out(operands[0], depth - 1) and all(_plain(part) for part in operands[1:])
    return False


def _made_by_a_call(form: Expression, depth: int) -> bool:
    """Whether a part is a string or a split's list a `WORKED_METHODS` or split call made, or a
    slice, a repeat, a character or a piece of one, or a join with one: a value no list
    argument holds."""
    if not isinstance(form, list) or not form or depth == 0:
        return False
    head, operands = form[0], form[1:]
    if head in WORKED_METHODS or head in LISTED_SPLITS:
        return True
    if head == "+":
        return any(_made_by_a_call(part, depth - 1) for part in operands)
    return head in ("[:]", "[]", "*") and _made_by_a_call(operands[0], depth - 1)


def _plain(part: Expression) -> bool:
    """A plain operand: a literal, an int, a bool or None."""
    return part is None or isinstance(part, int) or (isinstance(part, str) and part[:1] in "'\"")


# each method's arguments in the order Python takes them by position, with the default Python
# gives one left out; partition takes no keyword
_KEYWORDS: dict[str, tuple[tuple[str, object], ...]] = {
    "split": (("sep", None), ("maxsplit", -1)),
    "rsplit": (("sep", None), ("maxsplit", -1)),
    "splitlines": (("keepends", False),),
    "partition": (),
}


class _Listed(Protocol):
    """How a tracked list is made: its items, its form and its sink."""

    def made(self, items: list[object], expression: Expression, sink: BranchSink) -> object: ...


# the tracked list a split hands back, entered by `pyct.core.lists` as it is imported, which
# imports this module on its way
_LISTED: list[_Listed] = []


def enter_list(listed: _Listed) -> None:
    """Enter the tracked list type a split's pieces are handed back in."""
    _LISTED[:] = [listed]


def _by_position(
    name: str, args: tuple[object, ...], kwargs: dict[str, object]
) -> tuple[object, ...] | None:
    """A split's arguments as Python takes them by position: each keyword in its place, each
    one left out before it at Python's default. None for a call Python refuses, a keyword it
    does not take or one given twice, which the downgrade leaves to Python to refuse."""
    if not kwargs:
        return args
    names = _KEYWORDS[name]
    keys = [key for key, _ in names]
    if len(args) > len(keys) or any(key not in keys[len(args) :] for key in kwargs):
        return None
    last = max(keys.index(key) for key in kwargs)
    return (*args, *(kwargs.get(key, default) for key, default in names[len(args) : last + 1]))


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


def overlaps_itself(separator: str) -> bool:
    """Whether a separator's start can be its own end: ``aa``, ``aba``."""
    return any(separator[:size] == separator[-size:] for size in range(1, len(separator)))


def from_the_right(receiver: object, args: tuple[object, ...]) -> list[Expression] | None:
    """What an rsplit pyct encodes was called with, as a split's.

    With no limit, or one past `LONGEST_WALK`, the solver reads an rsplit as
    the split it matches, which it is unless its separator overlaps itself:
    ``"aaa".rsplit("aa")`` is ``["a", ""]`` where ``split`` finds ``["",
    "a"]``. So such an rsplit on such a separator is a form pyct does not
    encode. The check reads the plain separator, so it records nothing on the
    target's line.
    """
    parsed = _parsed(receiver, args)
    if parsed is None:
        return None
    operands, text, limit = parsed
    unwalked = limit < 0 or limit > LONGEST_WALK
    return None if unwalked and text is not None and overlaps_itself(text) else operands


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


def _on_the_plain_value(operation: Callable[..., Sequence[str]]) -> Callable[..., Sequence[str]]:
    """str's own split called on the plain text of the receiver and of each str argument.

    CPython may hand back an argument itself as a piece: the receiver, from
    partition where its separator is missing and from split where the
    separator is longer than the string, and the separator, as partition's
    middle piece. A tracked piece built from a tracked value reads its text
    through its `__str__`, a downgrade the target never made, and a
    downgrade's pieces would not be plain. On plain text every piece is
    plain, and pyct's call records nothing.
    """

    def call(receiver: object, *args: object, **kwargs: object) -> Sequence[str]:
        texts = [_text(arg) for arg in args]
        return operation(plain(receiver), *texts, **{key: _text(v) for key, v in kwargs.items()})

    return call


def _text(value: object) -> object:
    """A str argument as its plain text; any other argument as it is."""
    return plain(value) if isinstance(value, str) else value


def split_up(name: str, reader: Reader) -> Callable[..., object]:
    """str's own split, each piece a tracked str at its position in what Python built, in a
    tracked list whose form is the call, or partition's tuple.

    A form pyct does not encode is a downgrade whose pieces are all plain.
    """
    operation = _on_the_plain_value(getattr(str, name))
    downgrade = downgraded(str, name, calling=operation)

    def compute(self: Tracked, /, *args: object, **kwargs: object) -> object:
        taken = _by_position(name, args, kwargs)
        forms = None if taken is None else reader(self, taken)
        if taken is None or forms is None:
            return downgrade(self, *args, **kwargs)
        parts = own(operation, self, *taken)
        whole: Expression = [name, self.expression, *forms]
        pieces = list(_pieces(self, whole, parts))
        if isinstance(parts, tuple):
            return tuple(pieces)
        if not worked_out(self.expression):
            # a string the solver cannot work out from the input's values has no count it can
            # ask at; its pieces come back in Python's own list, as on origin/v2
            return pieces
        return _LISTED[0].made(pieces, whole, self.sink)

    return compute


def _pieces(receiver: Tracked, whole: Expression, parts: Iterable[str]) -> Iterable[object]:
    """Each piece of what Python built, tracked, carrying ``["[]", whole, k]``.

    Every piece holds the one ``whole``, so a program reads the split once.
    """
    return (piece(receiver, part, ["[]", whole, at]) for at, part in enumerate(parts))
