"""The summaries tool in a run: what a summaries ask is about, what it gives back, and the
provider that answers it.

``SummaryProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.summaries``.
Decision llm-summary-provider-declared-in-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyct.results.llm_asks import AskCost, Unanswered


@dataclass(frozen=True)
class ShownRun:
    """One recorded run of the loop as a request shows it: each name going in with its value at
    the start, and each changed name with its value at the end, each value JSON text."""

    going_in: tuple[tuple[str, str], ...]
    changed: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EarlierFormula:
    """An earlier try at this place that failed: the formula it gave, and why it failed."""

    formula: str
    reason: str


@dataclass(frozen=True)
class SummaryRequest:
    """What a summaries ask is about.

    ``place`` is the loop's site as the request and the recording name it, ``module:line:col``
    with the module's dotted name. ``code`` is the source of the function that holds the loop,
    the loop marked, then the code of the functions it calls in its package. ``parameters``
    are the formula's parameters, the names going in that every run shown holds; ``changed``
    the names the loop changes; ``runs`` the runs shown; ``tries`` the earlier tries at this
    place, oldest first.
    """

    place: str
    code: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    runs: tuple[ShownRun, ...]
    tries: tuple[EarlierFormula, ...] = ()


@dataclass(frozen=True)
class SummaryReply:
    """The reply's last fenced code block, as it came; ``ignored`` says why the reply held
    nothing the tool could read, such as no code block."""

    code: str
    cost: AskCost
    ignored: str | None = None


class SummaryProvider(Protocol):
    """Gives a loop's summary. It never raises for an LLM problem: it returns Unanswered."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered: ...
