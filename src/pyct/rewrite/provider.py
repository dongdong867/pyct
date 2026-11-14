"""What a rewrites ask is about, what it gives back, and the provider that answers it.

``RewriteProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.rewrites``.
Decision llm-rewrite-provider-declared-in-rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pyct.results.llm_asks import AskCost, Unanswered


@dataclass(frozen=True)
class Side:
    """A condition as Python writes it, and the side a path takes or a line needs."""

    text: str
    side: bool


@dataclass(frozen=True)
class EarlierTry:
    """A try at this moment that failed: the rewrite it gave, or the reply's text when it held
    none, why it failed, and whether the solver answered ``timeout`` or ``unknown`` to the
    rewrite's ask."""

    rewrite: str
    reason: str
    solver_gave_up: bool = False


@dataclass(frozen=True)
class RewriteRequest:
    """What a rewrites ask is about.

    ``place`` is the condition's site as the request and the recording name it,
    ``module:line:col`` with the module as the run names it. ``condition`` is the condition and
    the side the missed line needs; ``earlier`` the distinct conditions the path took before it,
    each at its last place, nearest last; ``code`` the source of the function that holds it;
    ``args`` each parameter with the input's value as JSON, or as Python writes it when JSON
    cannot hold it, and a value that holds an object as a placeholder written without running
    the target's code (``pyct.rewrite.request.value_text``); ``answer`` what the solver said,
    ``timeout`` or ``unknown``; ``tries`` this moment's earlier tries, oldest first, each saying
    whether the solver answered ``timeout`` or ``unknown`` to its rewrite's ask; and
    ``unreadable`` the parameters a rewrite may not read, since each holds an object.
    """

    place: str
    condition: Side
    earlier: tuple[Side, ...]
    code: str
    args: tuple[tuple[str, str], ...]
    answer: str
    tries: tuple[EarlierTry, ...] = ()
    unreadable: tuple[str, ...] = ()


@dataclass(frozen=True)
class RewriteReply:
    """The model's reply as it came, which ``pyct.rewrite.condition`` reads."""

    text: str
    cost: AskCost


class RewriteProvider(Protocol):
    """Rewrites a condition. It never raises for an LLM problem: it returns Unanswered."""

    def rewrite(self, request: RewriteRequest) -> RewriteReply | Unanswered: ...
