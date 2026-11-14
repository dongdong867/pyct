"""What a run says about its LLM tools as it goes, through ``Tell.noted``. Each tool adds its own.

The command line words each note; a note holds only the facts.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyct.core.foundation.branch import Site
from pyct.rewrite.notes import RewriteNote


@dataclass(frozen=True)
class AskSkipped:
    """A tool's ask got no reply, and why."""

    tool: str
    reason: str


@dataclass(frozen=True)
class ReplyIgnored:
    """A tool's reply held nothing the tool could read, and why."""

    tool: str
    reason: str


@dataclass(frozen=True)
class SeedDropped:
    """The LLM's seed at ``number`` in its reply, from 1, does not run, and why."""

    number: int
    reason: str


@dataclass(frozen=True)
class SeedsKept:
    """The places in the reply, from 1, of the LLM's seeds that run, in the order they run.
    Said before the first of them runs."""

    numbers: tuple[int, ...]


@dataclass(frozen=True)
class LimitReached:
    """The run's tokens reached ``--llm-limit``: no tool asks again this run. Said once."""


@dataclass(frozen=True)
class SummaryRead:
    """The formula the model's reply holds for the loop at ``site``, once it passes the form
    check: one line, or, with ``below``, statements the lines below it hold."""

    site: Site
    formula: str
    below: bool = False


@dataclass(frozen=True)
class SummaryChecked:
    """The formula for the loop at ``site`` gave each changed value of its ``runs`` recorded runs,
    and pyct follows the values it gives: it is kept."""

    site: Site
    runs: int


@dataclass(frozen=True)
class SummaryFailed:
    """Try ``attempt`` at the loop at ``site``, the connection's number, failed, and why."""

    site: Site
    attempt: int
    reason: str


@dataclass(frozen=True)
class SummarySkipped:
    """No summary is asked for or checked for the loop at ``site`` at this moment, and why."""

    site: Site
    reason: str


type SummaryNote = SummaryRead | SummaryChecked | SummaryFailed | SummarySkipped

# rewrites' own notes are declared in ``pyct.rewrite.notes``, which says them below this layer
type Note = (
    AskSkipped | ReplyIgnored | SeedDropped | SeedsKept | LimitReached | SummaryNote | RewriteNote
)
