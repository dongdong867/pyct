"""The loss sites' turns in a run's summaries tool, and the loss sites in use.

Before each pass picks a fork, the tool asks about each loss site an input
recorded a run of that had no turn this run, one at a time, in the order
recorded, with no stuck moment (``pyct.run.call_summaries``). Decision
llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it. While
the run's inputs run in pyct's own process no formula could come into use,
so a site gets no ask, said once in the run. A turn sends its ask through
the summaries tool (`pyct.run.summaries.Summaries`), which reads and checks
the reply as it does a loop's.

A formula that passed both checks comes into use from the next input on,
in core's table of loss sites in use (`pyct.core.entry.calls_in_use`), when
the run's inputs run in a process of their own and every answer its runs
recorded is an int, float, str or bool; else it is kept as checked, and why
is said once. Once it is in use, the latest input whose run its check used
runs again after the turn, labeled ``summary``. `CallTurns.took_out` also takes a site
out of use. Once the run's inputs run in pyct's own process, each site in use goes out
of use and is kept as checked, said once for each site.
"""

from __future__ import annotations

import os
import types
from collections.abc import Callable
from typing import Protocol

from pyct.core.entry import losses
from pyct.core.entry.in_use import CALLS_IN_USE
from pyct.core.foundation.branch import FormulaDrop, Site
from pyct.results.llm_asks import SummaryState
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.call_summaries import (
    CALL,
    LossSites,
    asked_call,
    call_request,
    failed_call_run,
    skipped_because,
)
from pyct.run.formula_runner import FormulaRunner, FormulaText, call_in_use
from pyct.run.loops_in_use import (
    IN_PYCT_S_PROCESS,
    dropped_because,
    kinds_unused_because,
    place_of,
)
from pyct.run.model_runs import CANNOT_FORK, can_fork
from pyct.run.notes import SummaryDropped, SummaryNotUsed, SummarySkipped
from pyct.run.stuck import LongAsk, Outcome, Running, going
from pyct.run.summary_asks import SummaryRequest
from pyct.run.summary_outcomes import Asked, LoopState, leave_use, take_out
from pyct.run.summary_runs import AskedLoop
from pyct.run.target import Target
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit

# why a loss site is not asked about: no run of it is recorded
NO_RECORDED_RUN = "no recorded run"
# the states of a loss site whose formula is kept
_KEPT = (SummaryState.IN_USE, SummaryState.CHECKED)


class Asking(Protocol):
    """What a loss site's turn uses of the summaries tool: each state an ask was sent for, where
    its notes are said, the run's token limit, the files the asks read code from, the target,
    whether the run's inputs run in a process of their own, the inputs to run again after the
    turn, a note said once, the ask itself, and a site's place as an ask names it."""

    loops: dict[Site, LoopState]
    told: Told
    limit: TokenLimit
    files: SourceFiles
    target: Target
    isolated: Callable[[], bool]
    again: list[int]

    def say_once(self, note: SummarySkipped | SummaryNotUsed) -> None: ...

    def asked(
        self, loop: AskedLoop, state: LoopState, request: SummaryRequest, run: Running
    ) -> tuple[Asked, bool]: ...

    def place(self, site: Site) -> str: ...


class CallsInUse:
    """A run's loss sites in use, by their sites, each in core's table until `close`."""

    def __init__(self) -> None:
        self.sites: set[Site] = set()

    def use(self, text: FormulaText, code: types.CodeType) -> None:
        """Put the formula's loss site in use from the next input on: its text, which names the
        site's downgrade and positions, and its code as pyct's process compiled it."""
        call = call_in_use(FormulaRunner(code, text, os.getpid()))
        if call is not None:
            # loaded here, in pyct's own process, so that each forked input has it
            losses.load_calls_in_use()
            self.sites.add(Site(*text.place))
            CALLS_IN_USE[text.place] = call

    def stop(self, site: Site) -> None:
        """Take the loss site at ``site`` out of use from the next input on."""
        self.sites.discard(site)
        CALLS_IN_USE.pop(place_of(site), None)

    def close(self) -> None:
        """Take each of the run's loss sites out of core's table, as the run ends."""
        for site in self.sites:
            CALLS_IN_USE.pop(place_of(site), None)
        self.sites.clear()


class CallTurns:
    """The loss sites the run's inputs recorded runs of, each one's turn, each site's positions
    as its last ask read them, and the sites in use."""

    def __init__(self, tool: Asking) -> None:
        self.tool = tool
        self.sites = LossSites()
        self.positions: dict[Site, tuple[str | None, ...]] = {}
        self.in_use = CallsInUse()

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
        if not tool.isolated():
            tool.say_once(SummarySkipped(site, IN_PYCT_S_PROCESS, call=name))
            return
        call = asked_call(site, name, run.records, tool.files)
        reason = NO_RECORDED_RUN if call is None else skipped_because(call)
        if call is None or reason is not None or not can_fork():
            tool.say_once(SummarySkipped(site, reason or CANNOT_FORK, call=name))
            return
        state = tool.loops.get(site) or LoopState(call.loop.piece.changed, kind=CALL, name=name)
        self.positions[site] = call.positions
        request = call_request(tool.target, call, tool.place(site), tool.files, state)
        tool.asked(call.loop, state, request, run)

    def used(
        self, loop: AskedLoop, name: str, text: str, file: str, code: types.CodeType
    ) -> SummaryState:
        """A loss site's formula that passed both checks, from its text, its code objects' file
        name and its code: in use when it can be, the input of its site's latest complete run
        kept to run again, else kept as checked and said with why."""
        site, changed = loop.site, loop.piece.changed
        tool = self.tool
        reason = (
            IN_PYCT_S_PROCESS if not tool.isolated() else kinds_unused_because(loop.runs, changed)
        )
        if reason is not None:
            tool.say_once(SummaryNotUsed(site, reason, call=name))
            return SummaryState.CHECKED
        place, positions = place_of(site), self.positions[site]
        formula = FormulaText(text, loop.parameters, changed, place, file, name, positions)
        self.in_use.use(formula, code)
        tool.again.append(loop.runs[-1].number)
        return SummaryState.IN_USE

    def heard(self, record: InputRecord, number: int) -> None:
        """An input the run kept as its input ``number``: each loss site it first recorded a run
        of is noted; each site in use its record says was dropped goes out of use, said with
        why; then, once the run's inputs run in pyct's own process, each site still in use goes
        out of use, kept as checked."""
        self.sites.heard(record)
        for drop in record.drops:
            if drop.site in self.in_use.sites:
                self._dropped(drop, record, number)
        self.fell_back()

    def _dropped(self, drop: FormulaDrop, record: InputRecord, number: int) -> None:
        """The site in use the input ``number`` dropped: out of use, said, its formula kept among
        its earlier tries with why, and the run it failed on, for its ask at the next turn."""
        site = drop.site
        self.in_use.stop(site)
        state = self.tool.loops[site]
        reason = dropped_because(drop)
        failed_on = failed_call_run(drop, record, number, self.tool.files)
        leave_use(state, f"dropped at input {number}: {reason}", failed_on)
        self.tool.told.note(SummaryDropped(site, number, reason, call=state.name))
        # asked about again at the next turn
        self.sites.turned.discard(site)

    def took_out(self, site: Site, long: LongAsk) -> None:
        """The site in use, taken out because the pick's ask ran long (``long``): out of use,
        said, its formula kept among its earlier tries with why, for its ask at the next turn."""
        if site not in self.in_use.sites:
            return
        self.in_use.stop(site)
        state = self.tool.loops[site]
        self.tool.told.note(take_out(state, site, long.number, long.reason))
        self.sites.turned.discard(site)

    def fell_back(self) -> None:
        """Once the run's inputs run in pyct's own process, each site still in use goes out of
        use, kept as checked, said once for each site."""
        if not self.in_use.sites or self.tool.isolated():
            return
        for site in sorted(self.in_use.sites, key=lambda site: (site.file, site.line, site.col)):
            self.in_use.stop(site)
            state = self.tool.loops[site]
            state.last = SummaryState.CHECKED
            self.tool.say_once(SummaryNotUsed(site, IN_PYCT_S_PROCESS, call=state.name))

    def came(self, site: Site | None) -> Outcome:
        """What came of the loss site at ``site``: ``took`` once its formula was checked or is in
        use, ``skipped`` while it, or with no site any site, waits for its turn, ``gave up``
        else."""
        waiting = self.sites.waiting()
        if site is None:
            return Outcome.SKIPPED if waiting else Outcome.GAVE_UP
        if site in waiting:
            return Outcome.SKIPPED
        state = self.tool.loops.get(site)
        if state is not None and state.kind == CALL and state.last in _KEPT:
            return Outcome.TOOK
        return Outcome.GAVE_UP
