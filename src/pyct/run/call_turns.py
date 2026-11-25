"""The loss sites' turns in a run's summaries tool, and the loss sites in use.

Before each pass picks a fork, the tool asks about each loss site an input
recorded a run of that had no turn this run, one at a time, in the order
recorded, with no stuck moment (``pyct.run.call_summaries``). Decision
llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it. While
the run's inputs run in pyct's own process no formula could come into use,
so a site gets no ask, said once in the run. A turn sends its ask through
the summaries tool (`pyct.run.summaries.Summaries`), which reads and checks
the reply.

A formula that passed both checks comes into use from the next input on,
in core's table of loss sites in use (`pyct.core.entry.calls_in_use`), when
the run's inputs run in a process of their own and every answer its runs
recorded is an int, float, str or bool; else it is kept as checked, and why
is said once. Once it is in use, the latest input whose run its check used
runs again after the turn, labeled ``summary``. Once the run's inputs run in
pyct's own process, each site in use goes out of use and is kept as
checked, said once for each site.
"""

from __future__ import annotations

import json
import os
import types
from collections.abc import Callable, Sequence
from typing import Protocol

from pyct.core.entry import losses
from pyct.core.entry.in_use import CALLS_IN_USE
from pyct.core.foundation.branch import DropReason, FormulaDrop, Site
from pyct.results.llm_asks import SummaryState
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.call_summaries import (
    CHANGED,
    AskedCall,
    LossSites,
    asked_call,
    call_request,
    failed_call_run,
    skipped_because,
)
from pyct.run.formula_runner import FormulaRunner, FormulaText, call_in_use
from pyct.run.model_runs import CANNOT_FORK, can_fork
from pyct.run.notes import SummaryDropped, SummaryNotUsed, SummarySkipped
from pyct.run.stuck import Outcome, Running, going
from pyct.run.summary_asks import EarlierFormula, SummaryRequest
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_outcomes import Asked, SiteState
from pyct.run.target import Target
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit

# why a loss site is not asked about: no run of it is recorded
NO_RECORDED_RUN = "no recorded run"
# why a formula is not used: the run's inputs run in pyct's own process
IN_PYCT_S_PROCESS = "inputs run in pyct's own process"
# the states of a loss site whose formula is kept
_KEPT = (SummaryState.IN_USE, SummaryState.CHECKED)
# the kinds of the answers a loss site in use can give
_KINDS = (int, float, str, bool)
# each other kind a value's JSON text reads as, in plain words
_OTHER_KINDS: dict[type, str] = {list: "a list", dict: "a dict", type(None): "None"}


class Asking(Protocol):
    """What a loss site's turn uses of the summaries tool: each state an ask was sent for, where
    its notes are said, the run's token limit, the files the asks read code from, the target,
    whether the run's inputs run in a process of their own, the inputs to run again after the
    turn, a note said once, the ask itself, and a site's place as an ask names it."""

    sites: dict[Site, SiteState]
    told: Told
    limit: TokenLimit
    files: SourceFiles
    target: Target
    isolated: Callable[[], bool]
    again: list[int]

    def say_once(self, note: SummarySkipped | SummaryNotUsed) -> None: ...

    def asked(
        self, call: AskedCall, state: SiteState, request: SummaryRequest, run: Running
    ) -> tuple[Asked, bool]: ...

    def place(self, site: Site) -> str: ...


class CallsInUse:
    """A run's loss sites in use, by their sites, each in core's table until `close`."""

    def __init__(self) -> None:
        self.sites: set[Site] = set()

    def use(self, text: FormulaText, code: types.CodeType) -> None:
        """Put the formula's loss site in use from the next input on: its text, which names the
        site's downgrade and positions, and its code as pyct's process compiled it."""
        # loaded here, in pyct's own process, so that each forked input has it
        losses.load_calls_in_use()
        self.sites.add(Site(*text.place))
        CALLS_IN_USE[text.place] = call_in_use(FormulaRunner(code, text, os.getpid()))

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
        state = tool.sites.get(site) or SiteState(CHANGED, name)
        self.positions[site] = call.positions
        request = call_request(tool.target, call, tool.place(site), tool.files, state)
        tool.asked(call, state, request, run)

    def used(self, call: AskedCall, text: str, file: str, code: types.CodeType) -> SummaryState:
        """A loss site's formula that passed both checks, from its text, its code objects' file
        name and its code: in use when it can be, the input of its site's latest complete run
        kept to run again, else kept as checked and said with why."""
        site, name = call.site, call.name
        tool = self.tool
        reason = (
            IN_PYCT_S_PROCESS if not tool.isolated() else kinds_unused_because(call.runs, CHANGED)
        )
        if reason is not None:
            tool.say_once(SummaryNotUsed(site, reason, call=name))
            return SummaryState.CHECKED
        place, positions = place_of(site), self.positions[site]
        formula = FormulaText(text, call.parameters, CHANGED, place, file, name, positions)
        self.in_use.use(formula, code)
        tool.again.append(call.runs[-1].number)
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
        state = self.tool.sites[site]
        state.last = SummaryState.DROPPED
        reason = dropped_because(drop)
        state.tries.append(
            EarlierFormula(state.formula or "", f"dropped at input {number}: {reason}")
        )
        state.failed_on = failed_call_run(drop, record, number, self.tool.files)
        self.tool.told.note(SummaryDropped(site, number, reason, call=state.name))
        # asked about again at the next turn
        self.sites.turned.discard(site)

    def fell_back(self) -> None:
        """Once the run's inputs run in pyct's own process, each site still in use goes out of
        use, kept as checked, said once for each site."""
        if not self.in_use.sites or self.tool.isolated():
            return
        for site in sorted(self.in_use.sites, key=lambda site: (site.file, site.line, site.col)):
            self.in_use.stop(site)
            state = self.tool.sites[site]
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
        state = self.tool.sites.get(site)
        if state is not None and state.last in _KEPT:
            return Outcome.TOOK
        return Outcome.GAVE_UP


def dropped_because(drop: FormulaDrop) -> str:
    """Why an input's run of a loss site dropped its formula, in plain words, each value its JSON
    text: the site's answer and the formula's, the raise's type, or the name it gave no value."""
    if drop.reason is DropReason.MISMATCH:
        return f"{drop.name} was {drop.value}, the formula gave {drop.got}"
    if drop.reason is DropReason.RAISED:
        return f"the formula raised {drop.got}"
    return f"the formula gave no {drop.name}"


def kinds_unused_because(runs: Sequence[CompleteRun], changed: Sequence[str]) -> str | None:
    """Why a checked formula does not come into use by what its runs recorded, or None when it
    may: a changed value of one of them is not an int, float, str or bool."""
    for each in runs:
        for value in each.run.changed:
            kind = _kind(value.value) if value.name in changed else None
            if kind is not None:
                return f"{value.name} is {kind}"
    return None


def _kind(text: str) -> str | None:
    """What a recorded value's JSON text holds, in plain words, when it is not an int, float,
    str or bool: ``a list``, ``a dict`` or ``None``, and ``unreadable`` for text JSON does not
    read; None when it is one of those four."""
    try:
        value = json.loads(text)
    except ValueError:
        return "unreadable"
    if isinstance(value, _KINDS):
        return None
    return _OTHER_KINDS[type(value)]


def place_of(site: Site) -> tuple[str, int, int]:
    """The site as core's table keys a loss site in use: its file, line and column."""
    return (site.file, site.line, site.col)
