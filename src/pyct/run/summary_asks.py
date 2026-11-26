"""What a summaries ask about a loss site is about and gives back, and the provider that answers
it.

``SummaryProvider`` is declared here, in the run layer that consumes it (``pyct.run.summaries``),
and implemented in ``pyct.llm.summaries``. Decision llm-summary-provider-declared-in-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.summary_runs import ShownRun


@dataclass(frozen=True)
class EarlierFormula:
    """An earlier try at this place that failed: the formula it gave, and why it failed."""

    formula: str
    reason: str


@dataclass(frozen=True)
class CallAsk:
    """What an ask about a loss site says of it: the downgrade's name, the site's code as written,
    and, for a watched call, its callee's module and qualified name, and whether the callee's
    source follows the code, None for an operation or a `math` call."""

    name: str
    written: str
    callee: str | None = None
    callee_source: bool = False


@dataclass(frozen=True)
class SummaryRequest:
    """What a summaries ask is about.

    ``place`` is the loss site's site as the request and the recording name it,
    ``module:line:col`` with the module's dotted name. ``code`` is the source of the function
    that holds it, the site marked, then the code of the functions it calls in its package,
    then, for a watched call, its callee's. ``parameters`` are the formula's parameters, the
    values going in named as the code writes them; ``changed`` is ``answer``; ``runs`` the runs
    shown; ``call`` what the ask says of the site; ``tries`` the earlier tries at this place,
    oldest first; ``not_shown`` the complete runs whose values going in no shown run has.
    """

    place: str
    code: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    runs: tuple[ShownRun, ...]
    call: CallAsk
    tries: tuple[EarlierFormula, ...] = ()
    not_shown: int = 0


@dataclass(frozen=True)
class SummaryReply:
    """The reply's last fenced code block, as it came; ``ignored`` says why the reply held
    nothing the tool could read, such as no code block."""

    code: str
    cost: AskCost
    ignored: str | None = None


class SummaryProvider(Protocol):
    """Gives a loss site's summary. It never raises for an LLM problem: it returns Unanswered."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered: ...
