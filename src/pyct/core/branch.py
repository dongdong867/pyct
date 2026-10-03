"""A fork the target took, a fact its path holds, a condition it lost, and where they go."""

from __future__ import annotations

import itertools
import os
import sys
import types
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# a condition, operator first. A leaf is a parameter's name or the access that reaches a value
# inside one: ["<", "x", 10], [">", ["[]", "items", 0], 5]. A float literal is the exact double
# the target held, NaN, the infinities and -0.0 included. None is a slice's missing bound,
# ["[:]", "s", 2, None], and prints as null
type Expression = list[Expression] | str | int | float | bool | None

# whether a list is a leaf: the access that names a value inside an argument, which a condition
# names as a value, never opens as an operation, and counts as one node
type IsLeaf = Callable[[Expression], bool]

# pyct's own package directory: every frame inside it is pyct, not the target.
# Unresolved, because a frame's co_filename is the unresolved __file__ it was compiled from.
PYCT_DIR = f"{Path(__file__).parent.parent}{os.sep}"
# the folder that holds pyct's package: a fresh interpreter imports pyct from here, so it runs
# the pyct this process runs
PYCT_ROOT = str(Path(__file__).parent.parent.parent)


@dataclass(frozen=True)
class Site:
    """Where in the target a fork happened. ``col`` is 0-based."""

    file: str
    line: int
    col: int


@dataclass(frozen=True)
class Branch:
    """One fork: the condition, the side the run took, and the position.

    ``raising`` marks a fork recorded before an operation that may raise, such
    as division's zero fork, rather than where a value is tested for truth.
    Both can sit at one column, as in ``if s[0] != s[0]:``, so only the mark
    tells whose side a fork took.

    ``lost_as`` names the operation that took it, which a call that is over names its loss by
    when a value it kept records one (see ``execution.tally``). It is not part of the fork, and
    it is not printed.

    ``is_held`` is set on a fork an `is` records as it tests its operand, and says whether the
    `is` held on that pass; None on any other fork. see-why reads an `is` test's sides from it
    (``results.senses``). Like ``lost_as``, it is not part of the fork, and it is not printed.
    """

    expression: Expression
    taken: bool
    site: Site
    raising: bool = False
    lost_as: str = field(default="__bool__", compare=False)
    is_held: bool | None = field(default=None, compare=False)

    @property
    def where(self) -> ForkSite:
        """The fork's site, told apart from another kind of fork at the same column."""
        return ForkSite(self.site, self.raising)


@dataclass(frozen=True)
class Fact:
    """Something the path holds that no input taking it can change, kept beside the forks.

    ``expression`` is a check whose answer pyct's own values already knew when the target ran
    it, held in the sense Python took (``taken``), or None for a fact that is only a place.
    ``place`` is which key a walk over a dict read at its place (see ``core.dict_reads``), or
    None; a lookup's, which holds whether or not a fork reads the value there, is written
    ``["given", place]``. A fact is never a fork: no input line lists it, pyct never aims at
    it, and the solver holds it true as recorded and never negates it.

    ``after`` is how many forks the input recorded before it, which the tally sets: a plan
    aimed at fork ``d`` keeps the facts whose ``after`` is at most ``d``. ``lost_as`` names the
    operation, as a fork's does.
    """

    expression: Expression
    taken: bool
    site: Site
    raising: bool = False
    place: Expression = None
    after: int = 0
    lost_as: str = field(default="__bool__", compare=False)

    @property
    def decided(self) -> bool:
        """Whether the fact is a check whose answer pyct already knew, rather than a place only."""
        return self.expression is not None

    def placed_after(self, forks: int) -> Fact:
        """This fact, recorded after ``forks`` forks."""
        return Fact(
            self.expression, self.taken, self.site, self.raising, self.place, forks, self.lost_as
        )

    @property
    def where(self) -> ForkSite:
        """The fact's site, told apart from an operation's fork before a raise at the same
        column."""
        return ForkSite(self.site, self.raising)


@dataclass(frozen=True)
class ForkSite:
    """A fork's site, and whether it is an operation's before a raise.

    What tells two forks at one column apart: ``if s[0] != s[0]:`` records
    the index's fork and the test's at the same line and column.
    """

    site: Site
    raising: bool = False


@dataclass(frozen=True)
class Downgrade:
    """One operation pyct has not taught, and where it was called.

    ``name`` is a method name or a dunder. ``site`` is found as a fork's is:
    the innermost code outside pyct that made the call.
    """

    name: str
    site: Site


# what a sink holds: the forks, the facts and the downgrades, in the order they happened
type SinkItem = Branch | Fact | Downgrade


class BranchSink(Protocol):
    """Where forks, facts and downgrades go, in the order they happened.

    core defines the one method and pushes, never reads. A plain list
    serves in tests; a real tree serves in a run. The parameter is
    positional-only, which is how ``list.append`` takes it.
    """

    def append(self, item: SinkItem, /) -> None: ...


# each instruction's site, by its code's id and offset, found once: a loop that forks or
# downgrades at one place asks on every pass, and finding the column walks the code's
# positions. The code is held weakly, so an id a freed code leaves behind is never read as it
_SITES: dict[tuple[int, int], tuple[weakref.ref[types.CodeType], Site]] = {}


# the last instruction a site was found for, and its site: a loop's repeat asks for it. One
# tuple, set in one store, so the alarm landing mid-update never pairs one with another's site
_LAST: list[tuple[types.CodeType | None, int, Site]] = [(None, -1, Site(file="", line=0, col=0))]


def caller_site() -> Site:
    """The position of the innermost frame outside pyct.

    A fork belongs to the target that tested the condition, so the walk
    steps over pyct's own frames. The column comes from the running
    instruction's position, which spans the expression being tested.
    """
    return site_of(sys._getframe(1))


def site_of(frame: types.FrameType | None) -> Site:
    """The position of ``frame``, or of the innermost frame outside pyct that called it.

    A caller that knows its own caller hands that frame in, which spares the
    walk one step on a path a loop runs on every pass.
    """
    # the last site found is outside pyct, so a repeat of it needs no walk
    last_code, last_at, last_site = _LAST[0]
    if frame is not None and frame.f_code is last_code and frame.f_lasti == last_at:
        return last_site
    while frame is not None and frame.f_code.co_filename.startswith(PYCT_DIR):
        frame = frame.f_back
    if frame is None:
        raise RuntimeError("no frame outside pyct to record the fork against")
    code, at = frame.f_code, frame.f_lasti
    held = _SITES.get((id(code), at))
    if held is not None and held[0]() is code:
        site = held[1]
    else:
        # f_lasti counts bytes, co_positions() counts two-byte instructions, as in traceback.py
        _, _, col, _ = next(itertools.islice(code.co_positions(), at // 2, None))
        site = Site(file=code.co_filename, line=frame.f_lineno, col=0 if col is None else col)
        _SITES[(id(code), at)] = (weakref.ref(code), site)
    _LAST[0] = (code, at, site)
    return site


# the last downgrade recorded, with the instruction outside pyct that made it: a loop that loses
# one condition on every pass records the one object again. One tuple, set in one store
_LAST_LOST: list[tuple[types.CodeType | None, int, Downgrade | None]] = [(None, -1, None)]


def lost_at(name: str, frame: types.FrameType) -> Downgrade:
    """The downgrade ``name`` made from ``frame``, or from the frame outside pyct that called it.

    The same call at the same instruction is the same downgrade, so it is
    built once and handed back while the calls repeat.
    """
    code, at, last = _LAST_LOST[0]
    if last is not None and frame.f_code is code and frame.f_lasti == at and last.name == name:
        return last
    lost = Downgrade(name=name, site=site_of(frame))
    # site_of kept the frame outside pyct it read the site from
    held_code, held_at, _ = _LAST[0]
    _LAST_LOST[0] = (held_code, held_at, lost)
    return lost
