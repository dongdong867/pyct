"""The loss sites in use: a site whose answers a checked formula stands for, in a call that runs in
a process of its own (`pyct.core.entry.losses` calls this module as it hears each loss).

An upper layer puts each site in use in `pyct.core.entry.in_use.CALLS_IN_USE`,
by its file, line and column, before an input starts; `start` reads it then.
`pyct.core.entry.losses` loads this module only then, when the table holds a
site and the input's call runs alone, so that a plain run loads none of it. While the input
is live and its call runs alone, each time a site in use runs with the
downgrade the site is in use with, the target's real answer is computed as
it would be with no formula, then the formula is called on the values going
in as they are, tracked ones included, each value at a position its
parameter names, a constant left out: an operation's receiver and other
operands, a `math` call's arguments, or a watched call's arguments as the
watch was given them, each list or dict as a copy made then
(`pyct.core.entry.in_use.as_it_went_in`). Each fork, fact and downgrade the
formula records is placed at the site, and each fork it records names the
site.

The two answers are compared by their JSON text. On a match the target
gets the real answer tracked with the formula's term, and no downgrade is
recorded there; a formula answer with no term leaves the real answer plain,
and the downgrade is recorded as before. On a mismatch, a raise of an
``Exception`` or a missing ``answer``, the target gets the real answer
plain, the downgrade is recorded as before, the site is not used again in
the input, and the caller is handed a `FormulaDrop`. A raise that is not an
``Exception``, the deadline's, passes through.

A site does not apply, and the target gets the real answer as before, while
any formula runs, a loop's or a site's, so that a formula that reaches a site
in use does not call it; when the values going in are not as many as the
formula's positions; and when the real answer's type is not exactly int,
float, str or bool, so that the target never loses a subclass's own
attributes.
"""

from __future__ import annotations

import contextlib
import itertools
import reprlib
import types
from collections.abc import Mapping, Sequence
from typing import Any, cast, override

from pyct.core.entry import in_use
from pyct.core.entry.in_use import ANSWER, CALLS_IN_USE, CallInUse
from pyct.core.entry.plain_copy import SCALARS
from pyct.core.entry.waiting import json_text
from pyct.core.foundation.branch import Downgrade, DropReason, FormulaDrop, Site, placed_at
from pyct.core.lists.list_state import plain
from pyct.core.numbers.ints import ConcolicInt

# the containers a drop's text reads beside a dict, the items it reads of each, one past those
# `reprlib` writes, and how many levels deep, as `reprlib` writes them
_SEQUENCES = (list, tuple, set, frozenset)
_SHOWN, _DEEPEST = 7, 6
# the real answers a site in use hands on tracked: Python's own, never a subclass
_ANSWERS = frozenset({int, float, str, bool})

type _Place = tuple[str, int, int]


class _Live:
    """The live input's sites in use, when its call runs alone, none else, the files that hold
    them, the sites dropped in it, and, by the code and instruction a watched call starts at,
    whether it answered at a site in use, with the code held so its id stays its own."""

    __slots__ = ("answers", "dropped", "files", "sites")

    def __init__(self) -> None:
        self.sites: dict[_Place, CallInUse] = {}
        self.files: frozenset[str] = frozenset()
        self.dropped: set[_Place] = set()
        self.answers: dict[tuple[int, int], tuple[types.CodeType, bool]] = {}


LIVE = _Live()


def start(*, alone: bool) -> None:
    """An input goes live: its call uses the sites in `CALLS_IN_USE` now when it runs ``alone``
    in a process of its own."""
    LIVE.sites = dict(CALLS_IN_USE) if alone else {}
    LIVE.files = frozenset(file for file, _, _ in LIVE.sites)
    LIVE.dropped = set()
    LIVE.answers = {}


def forget() -> None:
    """The live input ends: no site is in use until the next `start`."""
    LIVE.sites = {}
    LIVE.files = frozenset()
    LIVE.dropped = set()
    LIVE.answers = {}


def keeps_given(code: types.CodeType, at: int) -> bool:
    """Whether a watched call that starts at instruction ``at`` of ``code``, in a file that holds
    a site in use, keeps its arguments as it is given them: unless a start there answered at a
    site not in use, so that only the site's own call copies its lists and dicts."""
    held = LIVE.answers.get((id(code), at))
    return held is None or held[0] is not code or held[1]


def answered_at(code: types.CodeType, at: int, site: Site) -> None:
    """A watched call that kept its arguments, started at instruction ``at`` of ``code``,
    answered at ``site``."""
    LIVE.answers[(id(code), at)] = (code, (site.file, site.line, site.col) in LIVE.sites)


def answered(
    lost: Downgrade, values: Sequence[object] | None, real: object
) -> tuple[object, FormulaDrop | None]:
    """What the target gets at the loss ``lost``, given the values going in, None when none were
    kept, and the real answer: the real answer tracked on a match, else the real answer; and
    the drop, when the formula was dropped on this run."""
    with contextlib.suppress(Exception):
        site = lost.site
        place = (site.file, site.line, site.col)
        call = LIVE.sites.get(place)
        if call is None or not _applies(call, lost, values, real) or place in LIVE.dropped:
            return real, None
        given = {
            name: value
            for name, value in zip(call.positions, cast(Sequence[object], values), strict=True)
            if name is not None
        }
        return _formed(place, site, call, given, real)
    return real, None


def _applies(
    call: CallInUse, lost: Downgrade, values: Sequence[object] | None, real: object
) -> bool:
    """Whether the site's formula is tried on this run: its downgrade's name, no formula running,
    the values as many as its positions, and a real answer of Python's own scalar types."""
    return (
        call.name == lost.name
        and in_use.USING.forming is None
        and values is not None
        and len(values) == len(call.positions)
        and type(real) in _ANSWERS
    )


def _formed(
    place: _Place, site: Site, call: CallInUse, given: Mapping[str, object], real: object
) -> tuple[object, FormulaDrop | None]:
    """The formula run on ``given`` at the site, and its answer compared with the real one."""
    try:
        got = placed_at(site, lambda: _forming(site, call, given))
    except Exception as error:
        return real, _dropped(place, site, real, type(error).__name__, DropReason.RAISED)
    if not isinstance(got, Mapping) or ANSWER not in got:
        return real, _dropped(place, site, real, "", DropReason.MISSING)
    result = got[ANSWER]
    text = json_text(result)
    if text is None or text != json_text(real):
        got_text = text if text is not None else _written(result)
        return real, _dropped(place, site, real, got_text, DropReason.MISMATCH)
    if type(result) not in SCALARS:
        return real, None
    tracked = cast(ConcolicInt, result)
    # the real answer is of the formula answer's kind, as their JSON texts are one
    made = type(tracked).made(cast(int, real), tracked.expression, tracked.sink)
    in_use.gave((made,), site)
    return made, None


def _forming(site: Site, call: CallInUse, given: Mapping[str, object]) -> Mapping[str, object]:
    """The formula's answer for the values ``given``, each fork it records naming ``site``."""
    in_use.USING.forming = site
    try:
        return call.formula(given)
    finally:
        in_use.USING.forming = None


def _written(value: object) -> str:
    """A formula answer with no JSON text as Python writes it, cut short (`reprlib`), read as
    plain values first (`_plain`), so that the tracked values it holds record nothing as it is
    written, or its type's name when that raises."""
    with contextlib.suppress(Exception):
        return reprlib.repr(_plain(value, _DEEPEST))
    return type(value).__name__


class _Cut:
    """What stands for the parts of an answer deeper than a drop's text reads."""

    @override
    def __repr__(self) -> str:
        return "..."


def _plain(value: object, depth: int) -> object:
    """A value with each tracked scalar its plain value, and a list, tuple, set, frozenset or
    dict a new one of Python's own with its first `_SHOWN` items, each read so, ``depth``
    levels deep: each read through its base type, never its own methods, so that reading it
    records nothing. Another value as it is."""
    held: Any = plain(value)
    kind = type(held)
    if not issubclass(kind, (dict, *_SEQUENCES)):
        return held
    if depth <= 0:
        return _Cut()
    if issubclass(kind, dict):
        pairs = itertools.islice(dict.items(held), _SHOWN)
        return {_plain(key, depth - 1): _plain(item, depth - 1) for key, item in pairs}
    base = next(each for each in _SEQUENCES if issubclass(kind, each))
    items = itertools.islice(base.__iter__(held), _SHOWN)
    return base(_plain(item, depth - 1) for item in items)


def _dropped(place: _Place, site: Site, real: object, got: str, reason: DropReason) -> FormulaDrop:
    """Drop the site's formula for the rest of the input: the drop, its run not yet placed."""
    LIVE.dropped.add(place)
    return FormulaDrop(site, ANSWER, json_text(real) or "", got, reason)
