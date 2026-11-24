"""What came of one loop's turn at a stuck moment, and what the moment hands back for each entry
summaries take, from what came of each loop and loss site the entry names
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
    """How one loop's turn at a moment ended."""

    CHECKED = enum.auto()
    FAILED = enum.auto()
    NOT_ASKED = enum.auto()
    # not asked, since no formula of the loop could come into use this run
    NEVER_USED = enum.auto()


@dataclass
class LoopState:
    """One loop an ask was sent for, across the run: the names it changes, the connection's last
    try number, the earlier tries that failed or were dropped, the last formula the model gave,
    the runs a formula was checked on once one is checked, what came of the last ask sent for
    it, unanswered until its answer is read, the run its last formula was dropped on, whether a
    formula of its was ever dropped, and the lines it was asked for. An ask the token limit
    refused sent nothing and changes none of these. A loss site's state is a loop's, named
    ``call`` with its downgrade's ``name``."""

    changes: tuple[str, ...]
    attempts: int = 0
    tries: list[EarlierFormula] = field(default_factory=list)
    formula: str | None = None
    checked_on: int | None = None
    last: SummaryState = SummaryState.UNANSWERED
    failed_on: CompleteRun | None = None
    dropped: bool = False
    # the missed lines, by file, of the entries that named the loop at its asks: what the loop's
    # asks were for, not what came of them, so two states compare without them
    asked_for: set[tuple[str, int]] = field(default_factory=set, compare=False)
    kind: str = "loop"
    name: str | None = None


def sources_of(entry: WhyEntry, kind: SourceKind) -> list[Source]:
    return [each for each in entry.sources or () if each.kind is kind]


def outcome(
    entry: WhyEntry, came: dict[Site, Asked], call_came: Callable[[Site | None], Outcome]
) -> Outcome:
    """``took`` when each loop and each loss site the entry names has a checked formula; ``gave
    up`` when a try at a loop failed or its reply was ignored, when no formula of one could come
    into use this run, or when a loss site's came to nothing (``call_came``); ``skipped`` else.
    An entry that names none is ``gave up`` once no loss site waits for its turn."""
    loops = [came[each.site] for each in sources_of(entry, SourceKind.LOOP)]
    calls = [call_came(each.site) for each in sources_of(entry, SourceKind.LOST)]
    if not loops and not calls:
        return call_came(None)
    if Asked.FAILED in loops or Asked.NEVER_USED in loops or Outcome.GAVE_UP in calls:
        return Outcome.GAVE_UP
    if all(each is Asked.CHECKED for each in loops) and all(c is Outcome.TOOK for c in calls):
        return Outcome.TOOK
    return Outcome.SKIPPED
