"""What came of one ask about a loss site, each site's state across the run, and what a stuck
moment hands back for each entry summaries take, from what came of each loss site the entry names
(``pyct.run.summaries``)."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field

from pyct.core.foundation.branch import Site
from pyct.results.causes import Source, SourceKind, WhyEntry
from pyct.results.llm_asks import SummaryState
from pyct.run.stuck import Outcome
from pyct.run.summary_asks import EarlierFormula
from pyct.run.summary_checks import CompleteRun


class Asked(enum.Enum):
    """How one ask about a loss site ended."""

    CHECKED = enum.auto()
    FAILED = enum.auto()
    NOT_ASKED = enum.auto()


@dataclass
class SiteState:
    """One loss site an ask was sent for, across the run: the names its formula gives a value,
    its downgrade's name, the connection's last try number, the earlier tries that failed or were
    dropped, the last formula the model gave, the runs a formula was checked on once one is
    checked, what came of the last ask sent for it, unanswered until its answer is read, and the
    run its last formula was dropped on. An ask the token limit refused sent nothing and changes
    none of these."""

    changes: tuple[str, ...]
    name: str
    attempts: int = 0
    tries: list[EarlierFormula] = field(default_factory=list)
    formula: str | None = None
    checked_on: int | None = None
    last: SummaryState = SummaryState.UNANSWERED
    failed_on: CompleteRun | None = None


def sources_of(entry: WhyEntry, kind: SourceKind) -> list[Source]:
    return [each for each in entry.sources or () if each.kind is kind]


def outcome(entry: WhyEntry, came: Callable[[Site | None], Outcome]) -> Outcome:
    """``took`` when each loss site the entry names has a checked formula; ``gave up`` when one's
    came to nothing (``came``); ``skipped`` else. An entry that names no loss site, such as one
    that names only a loop, is ``gave up`` once no loss site waits for its turn."""
    calls = [came(each.site) for each in sources_of(entry, SourceKind.LOST)]
    if not calls:
        return came(None)
    if Outcome.GAVE_UP in calls:
        return Outcome.GAVE_UP
    if all(each is Outcome.TOOK for each in calls):
        return Outcome.TOOK
    return Outcome.SKIPPED
