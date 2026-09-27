"""A join, `sep.join(items)`: with a tracked separator, or a plain one where the call-site
substitution hands it to pyct (`pyct.core.substitutes.join`).

The join reads its items once, as str's own join does, before it joins them: a tracked list by
its walk, so the walk's forks come first and say how many items the join holds on the path.
Its answer is str's own text. It is a tracked str, ``["join", sep, what]``, when the separator,
the list or an item is tracked, and str's own plain answer when nothing is. ``sep`` is the
separator's expression, or a literal of its text. ``what`` is a tracked list's form when its
walk kept it, and otherwise a list display of the items the join read, ``["[,]", ...]``, each
an item's expression or a literal of its text (``README.md › Rules › the stdout line``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from pyct.core.branch import BranchSink, Downgrade, Expression, caller_site
from pyct.core.str_operands import literal, plain, within_cvc5
from pyct.core.values import BASES, base_value, downgraded, own

if TYPE_CHECKING:
    from pyct.core.strs import ConcolicStr


class _Formed(Protocol):
    """What a join reads of a tracked list: its form, None once it is plain, and its sink."""

    expression: Expression | None
    sink: BranchSink


_DOWNGRADE = downgraded(str, "join")


def taught(self: ConcolicStr, /, *args: object, **kwargs: object) -> object:
    """``sep.join(items)`` on a tracked separator. Any other call, a keyword included, is str's
    own answer and a downgrade named `join`, or str's own raise."""
    if kwargs or len(args) != 1:
        return _DOWNGRADE(self, *args, **kwargs)
    return joined(self, args[0], type(self))


def joined(separator: str, iterable: object, tracked: type[ConcolicStr]) -> object:
    """str's own ``separator.join(iterable)``, tracked when anything in it is.

    ``tracked`` is the tracked str's type. What is not iterable is str's own
    refusal, in its words. A character past the last one cvc5 holds, in the
    separator or an item, is str's own answer and a downgrade named `join`
    (``README.md › Rules › string encodings``).
    """
    try:
        iterator = own(iter, iterable)
    except TypeError:
        return own(str.join, plain(separator), iterable)
    form = _form(iterable)
    items: list[object] = own(list, iterator)
    answer = _answer(plain(separator), items)
    if form is not None and cast(_Formed, iterable).expression is not form:
        # the walk turned the list plain: what the join read is its items
        form = None
    if type(separator) is not tracked and form is None and tracked not in set(map(type, items)):
        return answer
    sink = _sink(separator, iterable if form is not None else None, items, tracked)
    texts = [plain(separator), *(plain(item) for item in items if isinstance(item, str))]
    if not all(within_cvc5(text) for text in texts):
        sink.append(Downgrade(name="join", site=caller_site()))
        return answer
    what = form if form is not None else ["[,]", *(_item(item, tracked) for item in items)]
    expression = ["join", _item(separator, tracked), what]
    return tracked.made(answer, expression=expression, sink=sink)


def _answer(separator: str, items: list[object]) -> str:
    """str's own join of the items: their text, or the TypeError Python raises for the plain
    values, where an item that is not a str is named by the type it reports."""
    try:
        return own(str.join, separator, items)
    except TypeError:
        return own(str.join, separator, [_as_python_reads(item) for item in items])


def _form(iterable: object) -> Expression | None:
    """A tracked list's form before the join walks it, or None for anything else."""
    if BASES.get(type(iterable)) is not list:
        return None
    return cast(_Formed, iterable).expression


def _as_python_reads(item: object) -> object:
    """An item as str's own join reads it: a str's text, and a tracked value of another type as
    a plain value of the type it reports, so Python's refusal names that type."""
    if isinstance(item, str):
        return plain(item)
    base = BASES.get(type(item))
    return item if base is None else base_value(base)


def _sink(
    separator: str, iterable: object, items: list[object], tracked: type[ConcolicStr]
) -> BranchSink:
    """Where the join's condition goes: the tracked separator's sink, the tracked list's, or the
    first tracked item's."""
    if type(separator) is tracked:
        return cast(_Formed, separator).sink
    if BASES.get(type(iterable)) is list:
        return cast(_Formed, iterable).sink
    return next(cast(_Formed, item).sink for item in items if type(item) is tracked)


def _item(item: object, tracked: type[ConcolicStr]) -> Expression:
    """A str the join reads, as the solver reads it: its expression, or a literal of its text."""
    if type(item) is tracked:
        return cast(_Formed, item).expression
    return literal(item, tracked)
