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
    no seed of its own names them in its refusal. ``TIMED_OUT`` and ``PROVIDER`` end one ask,
    ``NOT_RECORDED`` ends one a replay's file holds no reply for, and ``LIMIT`` refuses one
    once the run's tokens reach ``--llm-limit``, before any request leaves.
    """

    NO_PACKAGE = "no package"
    NO_KEY = "no key"
    TIMED_OUT = "timed out"
    PROVIDER = "provider"
    NOT_RECORDED = "not recorded"
    LIMIT = "limit"


@dataclass(frozen=True)
class AskCost:
    """What one ask cost: its try number at its place, from 1, the tokens it spent in and out,
    the seconds pyct waited for it, whether a replay's file answered it, and the tokens the run
    has left under ``--llm-limit`` after it.

    A replayed reply's tokens are the ones its recording holds until the connection hands the
    reply to its tool, which then reads 0: a replay spends no tokens. The connection fills
    ``tokens_left`` as it hands the answer on; None says it is not known, as from a provider
    built outside the connection, and a tool stops asking only on a known 0.
    """

    attempt: int
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    replayed: bool = False
    tokens_left: int | None = None


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


@dataclass(frozen=True)
class LlmUse:
    """What a run's LLM tools did, which the summary line's ``llm`` entry writes: the model, a
    replay's the one its recording names; the tools switched on; the asks the model answered,
    the ones a replay's file answered, and the ones that got no answer; the tokens spent in
    and out in this run; and the seconds pyct waited, replayed asks included."""

    model: str
    tools: tuple[str, ...]
    asks: int = 0
    replayed: int = 0
    skipped: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


class SummaryState(StrEnum):
    """Where a loop summaries asked about stands: its last formula checked, or not."""

    CHECKED = "checked"
    FAILED = "failed"


@dataclass(frozen=True)
class LoopSummary:
    """One loop summaries sent an ask for, as the summary line's ``llm.summaries`` lists it: the
    file and the line and column the loop starts at, the names it changes, the last formula a
    reply held, None when no reply held one, the connection's last try number at its place, and
    the past runs its formula was checked on, None when none is checked."""

    file: str
    line: int
    col: int
    changes: tuple[str, ...]
    formula: str | None
    tries: int
    checked_on: int | None = None

    @property
    def state(self) -> SummaryState:
        return SummaryState.FAILED if self.checked_on is None else SummaryState.CHECKED
