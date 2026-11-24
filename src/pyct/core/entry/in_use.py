"""The loops in use: a loop whose runs a checked formula stands for, in a call that runs in a
process of its own (`pyct.core.entry.pieces` calls this module from its hooks).

An upper layer puts each loop in use in `IN_USE`, by its file, line and
column, before an input starts; `start` reads it then. While the input is
live and its call runs alone, each run of a loop in use starts plain: each
name going in that is bound and holds a tracked int, float, str or bool is
rebound to its plain value, and a ``for`` over a tracked str walks the plain
str. Lists and dicts stay as they are; the run keeps a copy of each list
or dict going in. A copy of Python's own is one level deep. A tracked one's
copy is tracked, one level deep, while it has a form and its length is the
one pyct last saw. Otherwise its copy is plain (`plain_copy`): each list,
tuple, dict, set and frozenset inside it, at every depth, a subclass of one
included, that is tracked or holds a tracked value is a plain copy too,
and each tracked int, float, str or bool in them, a dict's keys included,
is its plain value. A tuple or frozenset subclass, such as a namedtuple,
and Python's own OrderedDict, defaultdict and Counter keep their type; any
other subclass, one the target wrote, is a copy of its base type. Another
object, such as a dataclass instance, stays as it is, and so does a dict
or set with a key whose hash is not Python's own, as a frozen dataclass
instance's or an object's whose class defines its own; an Enum member's,
a date's and a UUID's are. The plain copy runs none of the methods the
target wrote for its containers, nor a hash or equality it wrote for its
keys; a tracked dict that holds such a key has none, and that run of the
loop is followed as written. Either copy records nothing, unless a
standard-library hash calls a key's own methods, as
`collections.abc.Set._hash` calls `__len__` and `__iter__`, and leaves the
target's own as it is. The names the start rebinds hold plain
values, so the loop records no fork on them; a list or dict going in is
the target's own, and the loop's reads of what it holds record as the
loop as written records them.

At the run's end the formula is called on the tracked values that went in,
each list or dict as the copy the start made, each fork, fact and downgrade
it records placed at the loop's site, and each changed name the frame has
bound is compared with the formula's value of it by
their JSON text, which records nothing. On a match each changed name whose
formula value is a tracked int, float, str or bool holds the loop's own
value with the formula's term; another formula value leaves the loop's
value as it is. On a mismatch, a raise, or a changed name the formula gives
no value for, the changed names stay as the loop left them, the sink is
handed a `FormulaDrop` once the run is recorded (`dropped`), naming that
run, also when the restore or the record raises, and the loop is followed
as written for the rest of the input; a run of the loop still open then, in
an outer frame, ends with no call: its names
going in that it does not change get their tracked values back, and its
changed names keep the loop's values. Either way each name going in that is
not one of the piece's changed names gets its tracked value back when the
frame still holds the plain value the start wrote.

A raise that is not an ``Exception``, the deadline's, passes through. A run
that ends by ``return`` or a raise reaches no end: its names stay plain,
and the next start of the loop in that frame drops it.

A fork the formula records, and a later fork of the input whose condition
holds the term of a value a formula gave there, name that formula's site
(`summed`), so that an input aimed at one says a formula gave it, and a
path that holds one says which formulas its forks read. A value a formula
built from another formula's value names both. A formula value whose term
is a bare name, a parameter handed back as it is, has no term of its own,
and the forks that read it name no formula.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.entry.frames import rebind
from pyct.core.entry.plain_copy import SCALARS, plain_copy
from pyct.core.entry.waiting import Key, Waiting, json_text, popped
from pyct.core.foundation.branch import (
    Branch,
    BranchSink,
    DropReason,
    Expression,
    FormulaDrop,
    Site,
    placed_at,
)
from pyct.core.lists.list_state import plain
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

# the tracked values a loop in use runs on plain, and a formula's value hands on
_SCALARS = SCALARS

type _Place = tuple[str, int, int]
# a part of a term, kept so that its id stays its own, and the sites of the formulas it names
type _Named = tuple[list[Expression], frozenset[Site]]
# a piece's names going in and its changed names
type _Names = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class LoopInUse:
    """A loop's formula: its parameters, the names it gives a value, and the call that takes
    each parameter's value by name and answers each changed name's value by name."""

    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    formula: Callable[[Mapping[str, object]], Mapping[str, object]]


# the loops in use, by the file, line and column of each
IN_USE: dict[_Place, LoopInUse] = {}

# the one name a loss site's formula gives a value for
ANSWER = "answer"


@dataclass(frozen=True)
class CallInUse:
    """A loss site's formula (`pyct.core.entry.calls_in_use`): the name of the downgrade it
    stands for, each value going in's parameter by its position, None for a constant the formula
    does not take, and the call that takes each parameter's value by name and answers
    ``answer``'s."""

    name: str
    positions: tuple[str | None, ...]
    formula: Callable[[Mapping[str, object]], Mapping[str, object]]


# the loss sites in use, by the file, line and column of each, which an upper layer fills as it
# fills `IN_USE`
CALLS_IN_USE: dict[_Place, CallInUse] = {}


class Run:
    """A run of a loop in use, waiting on its end: the loop, the piece's names, the values that
    went in, each list or dict as a copy made then, the plain values its start wrote, and where
    it waits. ``entry`` is the token the
    recording of the piece's runs gave this run."""

    __slots__ = ("drop", "entry", "key", "kept", "loop", "names", "place", "site", "written")

    def __init__(
        self, place: _Place, loop: LoopInUse, names: _Names, kept: dict[str, object], key: Key
    ) -> None:
        self.place = place
        self.site = Site(*place)
        self.loop = loop
        self.names = names
        self.kept = {name: as_it_went_in(each) for name, each in kept.items()}
        self.written = {name: plain(each) for name, each in kept.items() if type(each) in _SCALARS}
        self.key = key
        self.entry: object = None
        # the drop of the run's formula, until `dropped` hands it to the sink
        self.drop: FormulaDrop | None = None


class _Using:
    """The live input's loops in use: the lines they start at when its call uses them, none
    else, where its drops go, the loops dropped in it, each run waiting on its end, by line,
    the site of the formula running, and what `summed` knows of the input's terms."""

    __slots__ = ("clean", "dropped", "forming", "given", "lines", "reads", "sink", "waiting")

    def __init__(self) -> None:
        self.lines: frozenset[int] = frozenset()
        self.sink: BranchSink | None = None
        self.clear()

    def clear(self) -> None:
        self.dropped: set[_Place] = set()
        self.waiting: Waiting[Run] = {}
        self.forming: Site | None = None
        # the term of each value a formula gave in the input, by its id, with the sites of the
        # formulas that gave it
        self.given: dict[int, _Named] = {}
        # each part of a term known to be or to hold such a term, by its id, with the sites of
        # every formula whose term it is or holds
        self.reads: dict[int, _Named] = {}
        # the ids of the parts known to hold none, each reachable from a fork the input keeps
        self.clean: set[int] = set()


USING = _Using()


def start(sink: BranchSink, *, alone: bool) -> None:
    """An input goes live: its call uses the loops in `IN_USE` now when it runs ``alone`` in a
    process of its own, and hands its drops to ``sink``."""
    USING.clear()
    USING.sink = sink
    USING.lines = frozenset(line for _, line, _ in IN_USE) if alone else frozenset()


def forget() -> None:
    """The live input ends: no loop is in use until the next `start`."""
    USING.lines = frozenset()
    USING.sink = None
    USING.clear()


def entered(frame: types.FrameType, line: int, col: int, names: _Names) -> Run | None:
    """A run of a piece starts in the frame: when the piece is a loop in use, its run, its
    tracked values going in rebound plain."""
    with contextlib.suppress(Exception):
        place = (frame.f_code.co_filename, line, col)
        key = (id(frame), col)
        popped(USING.waiting, line, key)
        loop = IN_USE.get(place)
        if loop is None or place in USING.dropped:
            return None
        held = frame.f_locals
        run = Run(place, loop, names, {name: held[name] for name in names[0] if name in held}, key)
        rebind(frame, run.written)
        USING.waiting.setdefault(line, {})[key] = run
        return run
    return None


def over[Iterated](
    iterable: Iterated, frame: types.FrameType, line: int, col: int, names: _Names
) -> Iterated:
    """A ``for`` starts in the frame, as `entered`: what it iterates over, a tracked str plain
    when the loop is in use."""
    run = entered(frame, line, col, names)
    if run is not None and type(iterable) is ConcolicStr:
        return cast(Iterated, plain(iterable))
    return iterable


def left(frame: types.FrameType, line: int, col: int) -> Run | None:
    """A loop's run ends in the frame: its formula stands for it, unless the input dropped the
    formula while the run was open, which only restores the names. Hands back the run when its
    formula was dropped on it, its names not yet restored (`restored`), else None."""
    with contextlib.suppress(Exception):
        run = popped(USING.waiting, line, (id(frame), col))
        if run is None:
            return None
        if run.place in USING.dropped:
            _rebound(frame, run, {})
            return None
        held = frame.f_locals
        real = {name: held[name] for name in run.loop.changed if name in held}
        made = _finished(run, real)
        if made is None:
            return run
        _rebound(frame, run, made)
    return None


def assigned(frame: types.FrameType, run: Run, value: object) -> tuple[object, bool]:
    """An assignment's run ends in the frame with its value, as `left`: the value to store, the
    tracked one when the formula matches, and whether the formula was dropped on it, the names
    then not yet restored (`restored`)."""
    with contextlib.suppress(Exception):
        line = run.site.line
        waiting = USING.waiting.get(line)
        if waiting is None or waiting.get(run.key) is not run:
            return value, False
        popped(USING.waiting, line, run.key)
        if run.place in USING.dropped:
            _rebound(frame, run, {})
            return value, False
        stored = run.loop.changed[0]
        made = _finished(run, {stored: value})
        if made is None:
            return value, True
        _rebound(frame, run, made)
        return made.get(stored, value), False
    return value, False


def _finished(run: Run, real: Mapping[str, object]) -> dict[str, object] | None:
    """Each changed name's tracked value the formula gives, or None when it is dropped."""
    loop = run.loop
    given = {name: run.kept[name] for name in loop.parameters if name in run.kept}
    try:
        got = placed_at(run.site, lambda: _forming(run.site, loop, given))
    except Exception as error:
        return _dropped(run, real, next(iter(real), ""), type(error).__name__, DropReason.RAISED)
    made: dict[str, object] = {}
    for name, value in real.items():
        if not isinstance(got, Mapping) or name not in got:
            return _dropped(run, real, name, "", DropReason.MISSING)
        result = got[name]
        text = json_text(result)
        if text is None or text != json_text(value):
            return _dropped(run, real, name, text or "", DropReason.MISMATCH)
        if type(result) in _SCALARS:
            tracked = cast(ConcolicInt, result)
            # the loop's value is of the formula value's kind, as their JSON texts are one
            real_value = cast(int, plain(value))
            made[name] = type(tracked).made(real_value, tracked.expression, tracked.sink)
    gave(made.values(), run.site)
    return made


def _forming(site: Site, loop: LoopInUse, given: Mapping[str, object]) -> Mapping[str, object]:
    """The formula's values for the values ``given``, each fork it records naming the loop at
    ``site`` (`summed`)."""
    USING.forming = site
    try:
        return loop.formula(given)
    finally:
        USING.forming = None


def gave(values: Iterable[object], place: Site) -> None:
    """Keep the term of each tracked value the formula at ``place`` gave, for `summed`. A term a
    walk already reached that now names one more formula, as when a formula hands back a term it
    was given, makes `summed` forget what its walks found: each part above it is out of date."""
    for each in values:
        term = _term(each)
        if not isinstance(term, list):
            continue
        key = id(term)
        _, sites = USING.given.get(key, (term, frozenset()))
        USING.given[key] = (term, sites | {place})
        known = USING.reads.get(key)
        if (known is not None and place not in known[1]) or key in USING.clean:
            USING.reads.clear()
            USING.clean.clear()


def _term(value: object) -> Expression:
    return cast(ConcolicInt, value).expression


def summed(fork: Branch) -> Branch:
    """The fork, naming the site of the formula running, which recorded it, and of each formula
    whose value's term its condition holds, as the very list, in code order; else the fork
    itself. A part is walked once in the input, unless `gave` makes the walks start over."""
    forming = USING.forming
    if forming is None and not USING.given:
        return fork
    sites = _formulas_read(fork.expression)
    if forming is not None:
        sites |= {forming}
    if not sites:
        return fork
    named = tuple(sorted(sites, key=dataclasses.astuple))
    return dataclasses.replace(fork, formulas=named)


def _formulas_read(expression: Expression) -> frozenset[Site]:
    """The sites of the formulas whose terms the expression is or holds. Each part walked joins
    ``USING.reads`` with the sites it names, or ``USING.clean`` when it names none, so that no
    later walk in the input goes below it."""
    if not isinstance(expression, list):
        return frozenset()
    reads, clean, given = USING.reads, USING.clean, USING.given
    pending: list[tuple[list[Expression], bool]] = [(expression, False)]
    while pending:
        part, below = pending.pop()
        key = id(part)
        if key in reads or key in clean:
            continue
        if not below:
            pending.append((part, True))
            pending.extend((each, False) for each in part if isinstance(each, list))
            continue
        sites = _named(part, given, reads)
        if sites:
            reads[key] = (part, sites)
        else:
            clean.add(key)
    held = reads.get(id(expression))
    return frozenset() if held is None else held[1]


def _named(
    part: list[Expression], given: dict[int, _Named], reads: dict[int, _Named]
) -> frozenset[Site]:
    """The sites a part names, each list in it already walked: its own, when a formula gave it,
    and those of each list in it."""
    own: frozenset[Site] = given[id(part)][1] if id(part) in given else frozenset()
    inside = (reads[id(each)][1] for each in part if isinstance(each, list) and id(each) in reads)
    return own.union(*inside)


def _dropped(run: Run, real: Mapping[str, object], name: str, got: str, reason: DropReason) -> None:
    """Drop the run's loop for the rest of the input, and keep the drop with the run for
    `dropped`."""
    USING.dropped.add(run.place)
    value = json_text(real[name]) if name in real else None
    run.drop = FormulaDrop(run.site, name, value or "", got, reason)


def restored(frame: types.FrameType, run: Run) -> None:
    """A run whose formula was dropped on it ends in the frame: each name going in that is not
    one of the piece's changed names gets its tracked value back, as `_rebound` gives it."""
    with contextlib.suppress(Exception):
        _rebound(frame, run, {})


def dropped(run: Run, at: int | None) -> None:
    """Hand the sink the drop of the run's formula, once the run is recorded: ``at`` is its
    position among the input's recorded runs of the loop, None when it is not recorded."""
    with contextlib.suppress(Exception):
        drop = run.drop
        if drop is not None and USING.sink is not None:
            USING.sink.append(dataclasses.replace(drop, run=at))


def _rebound(frame: types.FrameType, run: Run, made: Mapping[str, object]) -> None:
    """Bind each changed name the formula gave a tracked value, and give each name going in that
    is not one of the piece's changed names its tracked value back where the frame still holds
    the plain value the start wrote. A changed name the formula gave none keeps the loop's
    value."""
    held = frame.f_locals
    back = dict(made)
    changed = run.names[1]
    for name, written in run.written.items():
        if name not in changed and name in held and held[name] is written:
            back[name] = run.kept[name]
    rebind(frame, back)


def as_it_went_in(value: object) -> object:
    """A list or dict going in as a copy of the list or dict itself, one level deep, taken on every
    run of a loop in use: a loop that adds, removes or replaces its items leaves the copy as it went
    in. A tracked one's copy is tracked by the same form and records no fork. One with no form, or
    whose length is not the one pyct last saw, gets a plain copy (`plain_copy`), which runs none of
    the methods the target wrote for its containers, nor a hash or equality it wrote for its keys,
    records nothing unless a standard-library hash runs a key's own methods, and leaves the target's
    own as it is. A tracked copy costs about 4 microseconds for a list of 100 items and 30 for
    1,000. A plain copy's cost grows with every item it reaches through lists, tuples, dicts, sets
    and frozensets: about 9 for a list of 100 ints and 85 for 1,000, about 1 more for each tuple or
    list it holds and 2.5 for each dict of three keys, as 1,300 for a heap of 1,000 tuples, and 400
    for a list that holds one list of 10,000 plain ints. Any other value as it is."""
    kind = type(value)
    if kind is ConcolicList:
        items = cast(ConcolicList, value)
        current = items.expression is not None and items.length() == len(items.shadow)
        return copy.copy(items) if current else plain_copy(items)
    if kind is ConcolicDict:
        pairs = cast(ConcolicDict, value)
        current = pairs.expression is not None and pairs.size() == len(pairs.shadow)
        return copy.copy(pairs) if current else plain_copy(pairs)
    if kind is list or kind is dict:
        return copy.copy(value)
    return value
