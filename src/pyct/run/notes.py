"""What a run says about its LLM tools as it goes, through ``Tell.noted``. Each tool adds its own.

The command line words each note; a note holds only the facts.
"""

from __future__ import annotations

from dataclasses import dataclass


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


type Note = AskSkipped | ReplyIgnored | SeedDropped | SeedsKept | LimitReached
