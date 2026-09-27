"""A fork the target took, a condition it lost, and where both are pushed."""

from __future__ import annotations

import itertools
import os
import sys
import types
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


@dataclass(frozen=True)
class Site:
    """Where in the target a fork happened. ``col`` is 0-based."""

    file: str
    line: int
    col: int


@dataclass(frozen=True)
class Branch:
    """One fork: the condition, the side the run took, and the position.

    ``lost_as`` names the operation that took it, which a call that is over names its loss by
    when a value it kept records one (see ``execution.tally``). ``holds`` is a fact about the
    input that holds once the fork went the way it went: which key a walk over a dict read at
    its place (see ``core.dict_reads``). The solver asserts it wherever a path keeps the fork,
    and drops it where the path flips it. Neither is part of the fork, and neither is printed.
    """

    expression: Expression
    taken: bool
    site: Site
    lost_as: str = field(default="__bool__", compare=False)
    holds: Expression = field(default=None, compare=False)


@dataclass(frozen=True)
class Downgrade:
    """One operation pyct has not taught. ``name`` is a method name or a dunder."""

    name: str


# what a sink holds: the forks and the downgrades, in the order they happened
type SinkItem = Branch | Downgrade


class BranchSink(Protocol):
    """Where forks and downgrades go, in the order they happened.

    core defines the one method and pushes, never reads. A plain list
    serves in tests; a real tree serves in a run. The parameter is
    positional-only, which is how ``list.append`` takes it.
    """

    def append(self, item: SinkItem, /) -> None: ...


def caller_site() -> Site:
    """The position of the innermost frame outside pyct.

    A fork belongs to the target that tested the condition, so the walk
    steps over pyct's own frames. The column comes from the running
    instruction's position, which spans the expression being tested.
    """
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(PYCT_DIR):
        frame = frame.f_back
    if frame is None:
        raise RuntimeError("no frame outside pyct to record the fork against")
    # f_lasti counts bytes, co_positions() counts two-byte instructions; traceback.py does the same
    _, _, col, _ = next(itertools.islice(frame.f_code.co_positions(), frame.f_lasti // 2, None))
    return Site(file=frame.f_code.co_filename, line=frame.f_lineno, col=0 if col is None else col)
