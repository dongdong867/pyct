"""A fork the target took, where it took it, and where forks are pushed."""

from __future__ import annotations

import itertools
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# a condition, operator first, parameter names as leaves: ["<", "x", 10]
type Expression = list[Expression] | str | int | bool

# pyct's own package directory: every frame inside it is pyct, not the target.
# Unresolved, because a frame's co_filename is the unresolved __file__ it was compiled from.
_PYCT_DIR = f"{Path(__file__).parent.parent}{os.sep}"


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


class BranchSink(Protocol):
    """Where forks go.

    core defines the one method and pushes, never reads. A plain list
    serves in tests; a real tree serves in a run. The parameter is
    positional-only, which is how ``list.append`` takes it.
    """

    def append(self, branch: Branch, /) -> None: ...


def caller_site() -> Site:
    """The position of the innermost frame outside pyct.

    A fork belongs to the target that tested the condition, so the walk
    steps over pyct's own frames. The column comes from the running
    instruction's position, which spans the expression being tested.
    """
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(_PYCT_DIR):
        frame = frame.f_back
    if frame is None:
        raise RuntimeError("no frame outside pyct to record the fork against")
    _, _, col, _ = next(itertools.islice(frame.f_code.co_positions(), frame.f_lasti // 2, None))
    return Site(file=frame.f_code.co_filename, line=frame.f_lineno, col=0 if col is None else col)
