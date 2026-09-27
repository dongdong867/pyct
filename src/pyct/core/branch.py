"""A fork the target took, a condition it lost, and where both are pushed."""

from __future__ import annotations

import itertools
import os
import sys
import types
import weakref
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Site:
    """Where in the target a fork happened. ``col`` is 0-based."""

    file: str
    line: int
    col: int


@dataclass(frozen=True)
class Branch:
    """One fork: the condition, the side the run took, and the position."""

    expression: Expression
    taken: bool
    site: Site


@dataclass(frozen=True)
class Downgrade:
    """One operation pyct has not taught, and where it was called.

    ``name`` is a method name or a dunder. ``site`` is found as a fork's is:
    the innermost code outside pyct that made the call.
    """

    name: str
    site: Site


# what a sink holds: the forks and the downgrades, in the order they happened
type SinkItem = Branch | Downgrade


class BranchSink(Protocol):
    """Where forks and downgrades go, in the order they happened.

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
