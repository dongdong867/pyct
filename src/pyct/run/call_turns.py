"""The loss sites' turns in a run's summaries tool: before each pass picks a fork, an ask about
each loss site an input recorded a run of that had no turn this run, one at a time, in the order
recorded, with no stuck moment (``pyct.run.call_summaries``). Decision
llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it.

A turn sends its ask through the summaries tool (`pyct.run.summaries.Summaries`), which reads and
checks the reply as it does a loop's.
"""

from __future__ import annotations

from typing import Protocol

from pyct.core.foundation.branch import Site
from pyct.results.llm_asks import SummaryState
from pyct.results.source_files import SourceFiles
from pyct.run.call_summaries import CALL, LossSites, asked_call, call_request, skipped_because
from pyct.run.model_runs import CANNOT_FORK, can_fork
from pyct.run.notes import SummaryNotUsed, SummarySkipped
from pyct.run.stuck import Outcome, Running, going
from pyct.run.summary_asks import SummaryRequest
from pyct.run.summary_outcomes import Asked, LoopState
from pyct.run.summary_runs import AskedLoop
from pyct.run.target import Target
from pyct.run.token_limit import TokenLimit

# why a loss site is not asked about: no run of it is recorded
NO_RECORDED_RUN = "no recorded run"


class Asking(Protocol):
    """What a loss site's turn uses of the summaries tool: each state an ask was sent for, the
    run's token limit, the files the asks read code from, the target, a note said once, the ask
    itself, and a site's place as an ask names it."""

    loops: dict[Site, LoopState]
    limit: TokenLimit
    files: SourceFiles
    target: Target

    def say_once(self, note: SummarySkipped | SummaryNotUsed) -> None: ...

    def asked(
        self, loop: AskedLoop, state: LoopState, request: SummaryRequest, run: Running
    ) -> tuple[Asked, bool]: ...

    def place(self, site: Site) -> str: ...


class CallTurns:
    """The loss sites the run's inputs recorded runs of, and each one's turn."""

    def __init__(self, tool: Asking) -> None:
        self.tool = tool
        self.sites = LossSites()

    def between(self, run: Running) -> None:
        """Ask about each loss site an input recorded a run of that had no turn this run, one at
        a time, in the order recorded, until the token limit is reached or the run is no longer
        going."""
        for site in self.sites.waiting():
            if self.tool.limit.reached or not going(run):
                return
            self.sites.turned.add(site)
            self._turn(site, run)

    def _turn(self, site: Site, run: Running) -> None:
        """A loss site's one turn this run: skipped and said, or asked about."""
        tool = self.tool
        name = self.sites.names[site]
        call = asked_call(site, name, run.records, tool.files)
        reason = NO_RECORDED_RUN if call is None else skipped_because(call)
        if call is None or reason is not None or not can_fork():
            tool.say_once(SummarySkipped(site, reason or CANNOT_FORK, call=name))
            return
        state = LoopState(call.loop.piece.changed, kind=CALL, name=name)
        request = call_request(tool.target, call, tool.place(site), (), tool.files)
        tool.asked(call.loop, state, request, run)

    def came(self, site: Site | None) -> Outcome:
        """What came of the loss site at ``site``: ``took`` once its formula was checked,
        ``skipped`` while it, or with no site any site, waits for its turn, ``gave up`` else."""
        waiting = self.sites.waiting()
        if site is None:
            return Outcome.SKIPPED if waiting else Outcome.GAVE_UP
        if site in waiting:
            return Outcome.SKIPPED
        state = self.tool.loops.get(site)
        if state is not None and state.kind == CALL and state.last is SummaryState.CHECKED:
            return Outcome.TOOK
        return Outcome.GAVE_UP
