"""A split the solver has no one formula for, built step by step as Python builds it.

``split`` and ``rsplit`` of a string the solver cannot work out from the input's values, or
by a tracked separator or limit, hand back Python's own list. Its pieces are tracked strs, each
the slice of the string between two places a step found, and each step records the fork it
decides, at the split's line, as CPython's own loop decides it:

- a tracked limit first: ``n < 0``, no limit, and then before each cut ``n > k``, that the
  limit allows cut k + 1; a plain limit decides nothing, a tracked bool is never negative, and
  a check the limit's range proves is a fact;
- a tracked separator next: ``d != ''``, before Python's ValueError for an empty one;
- each cut: ``s.find(sep, start) != -1``, that the rest from the end of the last piece holds
  another separator, or ``s.rfind(sep, 0, end) != -1`` from the right; by whitespace,
  ``s.nextword(i) != -1``, that a word starts at or past i, or ``s.lastword(j) != -1``, that
  one ends before j.

A word's edge is ``s.wordend(i)``, the first whitespace at or past i or the length, and
``s.wordstart(j)``, one past the last whitespace before j or 0; whitespace is every character
Python's ``isspace`` takes. The steps change no count the solver works out, so the list is
Python's own and its length plain: the forks above are what move it
(split-list-tracked-the-piece-there-a-tracked-index-at-its-value-and-the-rest-by-exact-steps).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt, known_range
from pyct.core.spans import proves
from pyct.core.str_cases import Tracked, piece
from pyct.core.str_operands import literal, plain, position
from pyct.core.values import forked, held, own

# the splits built by steps
STEPPED = frozenset({"split", "rsplit"})


@dataclass(frozen=True)
class _Limit:
    """A split's limit as CPython reads it: its value, -1 for none, and its form when tracked."""

    value: int
    form: Expression = None
    # the tracked int it is, which the walk checks for negative and whose range a check reads;
    # None for a tracked bool, and the int one is, which is never negative
    number: ConcolicInt | None = None


@dataclass(frozen=True)
class _Separator:
    """A split's separator: its text and form, and the form of its length; None for whitespace."""

    text: str | None
    form: Expression = None
    width: Expression = None
    tracked: bool = False


@dataclass
class _Steps:
    """One split being built: the string, the separator, the limit, and the pieces so far."""

    name: str
    receiver: Tracked
    text: str
    separator: _Separator
    limit: _Limit
    pieces: list[object] = field(default_factory=list)
    # whether the limit counts the cuts: a plain one of 0 or more, or a tracked one not negative
    counted: bool = True

    def fork(self, expression: Expression, taken: bool, *, raising: bool = False) -> bool:
        return forked(self.receiver.sink, expression, taken, self.name, raising=raising)

    def add(self, value: str, form: Expression) -> None:
        self.pieces.append(piece(self.receiver, value, form))

    def checks_limit(self, op: str, number: int, taken: bool) -> bool:
        """A check of a tracked limit as a tracked int's compare is tested: a fact where its
        range proves the answer, else a fork, which narrows a split's count."""
        expression: Expression = [op, self.limit.form, number]
        tracked = self.limit.number
        if tracked is not None:
            span = known_range(tracked)
            if span is not None and proves(span, op, number) is taken:
                return held(self.receiver.sink, expression, taken, self.name)
            if tracked.count is not None:
                tracked.count.narrow(op, number, taken)
        return self.fork(expression, taken)

    def allows(self) -> bool:
        """Whether the limit allows another cut, as CPython's ``maxcount-- > 0`` decides it."""
        cuts, limit = len(self.pieces), self.limit
        if not self.counted:
            return True
        if limit.form is None:
            return cuts < limit.value
        return self.checks_limit(">", cuts, limit.value > cuts)


def _limit(args: tuple[object, ...]) -> _Limit | None:
    """The limit a split pyct steps through is given: none, a plain int or bool, or a tracked
    int or bool; None for any other value, which pyct leaves to Python to answer or refuse."""
    if len(args) < 2:
        return _Limit(-1)
    value = args[1]
    if isinstance(value, ConcolicBool):
        return _Limit(int.__index__(value), ["int", value.expression])
    if isinstance(value, ConcolicInt):
        number = value if value.as_int is None else None
        return _Limit(int.__index__(value), value.expression, number)
    at = position(value)
    return None if at is None else _Limit(at)


def _separator(receiver: Tracked, args: tuple[object, ...]) -> _Separator | None:
    """The separator a split pyct steps through is given: None, a tracked str, or a plain str
    the solver holds; None for any other value."""
    value = args[0] if args else None
    if value is None:
        return _Separator(None)
    kind: type = type(receiver)
    if isinstance(value, kind):
        tracked = getattr(value, "expression", None)
        return _Separator(plain(value), tracked, ["len", tracked], tracked=True)
    written = literal(value, kind)
    if written is None:
        return None
    assert isinstance(value, str)
    return _Separator(plain(value), written, str.__len__(value))


def needs_steps(receiver: Tracked, args: tuple[object, ...], worked_out: bool) -> bool:
    """Whether a split's operands ask for steps: a tracked separator or limit, or a string the
    solver cannot work out, with operands the steps read."""
    if len(args) > 2 or _limit(args) is None or _separator(receiver, args) is None:
        return False
    kind: type = type(receiver)
    tracked = any(isinstance(arg, (ConcolicInt, ConcolicBool, kind)) for arg in args)
    return tracked or not worked_out


def stepped(name: str, receiver: Tracked, args: tuple[object, ...]) -> list[object]:
    """Python's own list for ``receiver.name(*args)``, each piece a tracked slice, the forks of
    its steps recorded; Python's own error for a call it refuses, after the forks before it."""
    separator, limit = _separator(receiver, args), _limit(args)
    assert separator is not None and limit is not None
    texts = [plain(arg) if isinstance(arg, str) else arg for arg in args]
    steps = _Steps(name, receiver, plain(receiver), separator, limit)
    if limit.form is None:
        steps.counted = limit.value >= 0
    elif limit.number is not None:
        steps.counted = not steps.checks_limit("<", 0, limit.value < 0)
    if separator.tracked:
        # the fork before Python's own ValueError for an empty separator
        steps.fork(["!=", separator.form, "''"], separator.text != "", raising=True)
    parts = own(getattr(str, name), steps.text, *texts)
    _WALKS[name, separator.text is None](steps)
    assert [plain(part) for part in steps.pieces] == parts, (steps.pieces, parts)
    return steps.pieces


def _by_separator(steps: _Steps) -> None:
    """``split`` by a separator: each cut a search from the end of the last piece."""
    form, sep = steps.receiver.expression, steps.separator
    assert sep.text is not None
    start, at = 0, 0
    begun: Expression = None
    while steps.allows():
        found: Expression = ["find", form, sep.form] + ([] if begun is None else [begun])
        at = steps.text.find(sep.text, start)
        if not steps.fork(["!=", found, -1], at != -1):
            break
        steps.add(steps.text[start:at], ["[:]", form, begun, found])
        start, begun = at + len(sep.text), ["+", found, sep.width]
    steps.add(steps.text[start:], form if begun is None else ["[:]", form, begun, None])


def _by_separator_from_the_right(steps: _Steps) -> None:
    """``rsplit`` by a separator: each cut a search back from the start of the last piece."""
    form, sep = steps.receiver.expression, steps.separator
    assert sep.text is not None
    end = len(steps.text)
    ended: Expression = None
    while steps.allows():
        found: Expression = ["rfind", form, sep.form] + ([] if ended is None else [0, ended])
        at = steps.text.rfind(sep.text, 0, end)
        if not steps.fork(["!=", found, -1], at != -1):
            break
        after: Expression = ["+", found, sep.width]
        steps.add(steps.text[at + len(sep.text) : end], ["[:]", form, after, ended])
        end, ended = at, found
    steps.add(steps.text[:end], form if ended is None else ["[:]", form, None, ended])
    steps.pieces.reverse()


def _by_whitespace(steps: _Steps) -> None:
    """``split()``: each word from the next character that is not whitespace to the next one
    that is; past the limit, the rest from its first word on, if it holds one."""
    form, text = steps.receiver.expression, steps.text
    at = 0
    begun: Expression = 0
    while steps.allows():
        word: Expression = ["nextword", form, begun]
        start = next_word(text, at)
        if not steps.fork(["!=", word, -1], start != -1):
            return
        at, begun = word_end(text, start), ["wordend", form, word]
        steps.add(text[start:at], ["[:]", form, word, begun])
    word = ["nextword", form, begun]
    start = next_word(text, at)
    if steps.fork(["!=", word, -1], start != -1):
        steps.add(text[start:], ["[:]", form, word, None])


def _by_whitespace_from_the_right(steps: _Steps) -> None:
    """``rsplit()``: each word back from the last character before the last piece that is not
    whitespace; past the limit, the rest up to its last word, if it holds one."""
    form, text = steps.receiver.expression, steps.text
    end = len(text)
    ended: list[Expression] = []
    while steps.allows():
        word: Expression = ["lastword", form, *ended]
        last = last_word(text, end)
        if not steps.fork(["!=", word, -1], last != -1):
            steps.pieces.reverse()
            return
        start: Expression = ["wordstart", form, word]
        end, ended = word_start(text, last), [start]
        steps.add(text[end : last + 1], ["[:]", form, start, ["+", word, 1]])
    word = ["lastword", form, *ended]
    last = last_word(text, end)
    if steps.fork(["!=", word, -1], last != -1):
        steps.add(text[: last + 1], ["[:]", form, None, ["+", word, 1]])
    steps.pieces.reverse()


def next_word(text: str, at: int) -> int:
    """Where the first character at or past ``at`` that is not whitespace is, or -1."""
    return next((i for i in range(at, len(text)) if not text[i].isspace()), -1)


def word_end(text: str, at: int) -> int:
    """Where the first whitespace at or past ``at`` is, or the length."""
    return next((i for i in range(at, len(text)) if text[i].isspace()), len(text))


def last_word(text: str, end: int) -> int:
    """Where the last character before ``end`` that is not whitespace is, or -1."""
    return next((i for i in range(end - 1, -1, -1) if not text[i].isspace()), -1)


def word_start(text: str, end: int) -> int:
    """One past the last whitespace before ``end``, or 0."""
    return next((i + 1 for i in range(end - 1, -1, -1) if text[i].isspace()), 0)


# each walk by its method and whether it splits on whitespace
_WALKS: dict[tuple[str, bool], Callable[[_Steps], None]] = {
    ("split", False): _by_separator,
    ("rsplit", False): _by_separator_from_the_right,
    ("split", True): _by_whitespace,
    ("rsplit", True): _by_whitespace_from_the_right,
}
