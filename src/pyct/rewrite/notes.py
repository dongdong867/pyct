"""What rewrites say as they go, each fact the moment it happens. ``pyct.run.notes`` hands them on
through ``Tell.noted``, and the command line words each one."""

from __future__ import annotations

from dataclasses import dataclass

from pyct.core.foundation.branch import Site


@dataclass(frozen=True)
class RewriteRead:
    """The condition the model's reply holds for the condition at ``site``, before it runs."""

    site: Site
    expression: str


@dataclass(frozen=True)
class RewriteTook:
    """The rewrite's input took the side the missed line needs at ``site``: the rewrite is kept."""

    site: Site


@dataclass(frozen=True)
class RewriteFailed:
    """Try ``attempt`` at ``site``, the connection's number, failed, and why."""

    site: Site
    attempt: int
    reason: str


@dataclass(frozen=True)
class RewriteSkipped:
    """No rewrite runs for the condition at ``site`` at this moment, and why: pyct's process could
    not fork a child for it."""

    site: Site
    reason: str


@dataclass(frozen=True)
class RewriteGivenUp:
    """The condition at ``site`` is given up at this moment before any ask, and why: no parameter
    is left that a rewrite may read, each holding an object or the method taking only ``self``."""

    site: Site
    reason: str


@dataclass(frozen=True)
class RewriteDropped:
    """A kept rewrite at ``site`` is dropped: input ``number``, from 1, whose ask used it, took the
    other side."""

    site: Site
    number: int


type RewriteNote = (
    RewriteRead | RewriteTook | RewriteFailed | RewriteSkipped | RewriteGivenUp | RewriteDropped
)
