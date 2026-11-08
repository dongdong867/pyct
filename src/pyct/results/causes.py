"""A cause of uncovered lines, as the analysis gives it and the summary line writes it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pyct.core.foundation.branch import Site


class Reason(StrEnum):
    """Why a line was not run. The values are the words on the summary line."""

    IMPORT = "import"
    NOT_CALLED = "not called"
    NOT_TAKEN = "not taken"
    NO_FORK = "no fork"
    HANDLER = "handler"
    ENDED_BEFORE = "ended before"
    SUSPENDED = "suspended"
    NOT_WORKED_OUT = "not worked out"


@dataclass(frozen=True)
class Tries:
    """What happened each time the run could have flipped the forks at one site, and how many
    inputs ran a check there whose answer pyct's own values already knew (``decided``)."""

    not_tried: int = 0
    unsat: int = 0
    unknown: int = 0
    timeout: int = 0
    left_the_plan: int = 0
    decided: int = 0


@dataclass(frozen=True)
class Condition:
    """A condition on a line's way, by its site, and the side the line needs."""

    site: Site
    side: bool


class SourceKind(StrEnum):
    """Where a value a condition with no fork reads came from. The values are the words on the
    summary line."""

    LOOP = "loop"
    LOST = "lost"


@dataclass(frozen=True)
class Source:
    """One place the value came from, by the name it reached the condition through.

    A loop's ``site`` is its own ``for`` or ``while``, or its comprehension's
    start. A lost one's is the call's, and ``call`` names the downgrade the
    call recorded.
    """

    kind: SourceKind
    name: str
    site: Site
    call: str | None = None


@dataclass(frozen=True)
class WhyEntry:
    """One cause, and the lines of one file it accounts for, ascending.

    ``function`` is set for ``not called``, ``condition`` for ``not taken``
    and ``no fork``, ``tries`` for ``not taken``, ``sources`` for ``no
    fork``, empty when none was found, and ``at_yield``, the line of the
    ``yield`` the function was left at, for ``suspended``.
    """

    file: str
    lines: tuple[int, ...]
    reason: Reason
    function: str | None = None
    condition: Condition | None = None
    tries: Tries | None = None
    at_yield: int | None = None
    sources: tuple[Source, ...] | None = None
