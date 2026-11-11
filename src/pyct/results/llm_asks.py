"""What one ask of the LLM gave back: a reply, or the reason it got none, with what it cost.

These sit below every tool's consumer, so a provider declared in ``run/`` or ``rewrite/`` can
return them, and ``llm/`` builds them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Why(StrEnum):
    """Why an ask got no reply, or why no ask could be made.

    ``NO_PACKAGE`` and ``NO_KEY`` are found before the run, so no ask returns them; a run with
    no seed of its own names them in its refusal. ``TIMED_OUT`` and ``PROVIDER`` end one ask.
    """

    NO_PACKAGE = "no package"
    NO_KEY = "no key"
    TIMED_OUT = "timed out"
    PROVIDER = "provider"


@dataclass(frozen=True)
class AskCost:
    """What one ask cost: its try number at its place, from 1, the tokens it spent in and out,
    and the seconds pyct waited for it."""

    attempt: int
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class Reply:
    """The model's reply as it came, which the tool that asked reads."""

    text: str
    cost: AskCost


@dataclass(frozen=True)
class Unanswered:
    """An ask that got no reply: why, the words stderr gives after ``skipped: ``, and its cost.

    The reason is built from an error's class and HTTP status only, never its text, so no
    header or key can reach it.
    """

    why: Why
    reason: str
    cost: AskCost
