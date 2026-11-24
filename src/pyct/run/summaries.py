"""The summaries tool in a run: the stuck moment's summaries slot, what a summaries ask is about
and gives back, and the provider that answers it.

At a moment, summaries take each ``no fork`` entry, and ask once about each
distinct loop its sources name, in code order, however many entries name it.
A loop is asked about with its function's code, the loop marked, and its
complete runs: the runs of it the inputs so far recorded that hold every
name it changes, up to 3 per input, but those it holds back
(``pyct.run.summary_runs``). A loop no formula of which could come into
use, by its own code or since the run's inputs run in pyct's own process
(``pyct.run.loops_in_use.never_used_because``), a loop with no complete run,
and one asked about while pyct's process runs a second thread, so that no
formula could run, is skipped at this moment with no ask, and said the first
time this run it is skipped for that reason; the entries that name the
first are given up. An ask that got no answer is said
and ends that loop's tries at this moment; once an answer leaves no token
under the limit no summary is asked for again this run, the tool says it
can ask no more, and the connection has said so. A reply with no code block
is said and ends them too. The wait for the model pauses the run's clock. A
call a cause names gets no ask.

A reply's formula is read, checked for its form, then checked on the
loop's complete runs and for values pyct follows (``pyct.run.summary_checks``).
A formula that fails a check is a failed try, said with its reason and kept
for the loop's later asks; one that passes both is kept for its loop, and
that loop is not asked about again while it is kept. It comes into use from
the next input on, for the rest of the run or until an input drops it, when
it can (``pyct.run.loops_in_use``); else it is kept as checked, and why is
said right after the line that says it passed, once in the run for each loop
and reason. A check whose child could not start, or that the run's deadline
ended, is no try: the loop is skipped at this moment, and said. After the
moment's asks, the latest input whose run of each loop that came into use
then its formula was checked on runs again, labeled ``summary``, each such
input once, so that the formulas give the solver their forks at once; a
moment that put no formula in use runs no input.

The tool hears each input the run keeps. A loop in use that an input's
record says was dropped goes out of use from the next input on, and its
drop is said with the input's number and why. The loop is asked about
again at each later moment while a line it was asked for is still missed
and no formula of its is in use or checked since, whether or not an entry
names it and whatever came of an ask since, its dropped formula among the
earlier tries with why, and the run it failed on first among the runs
shown. Once
the run's inputs run in pyct's own process, each loop in use goes out of use
and is kept as checked, said once for each loop.

The summary line lists each loop an ask was sent for with what came of its
last ask sent (``SummaryState``): its formula in use, checked and not used,
or dropped; failed, by a check or a reply with no code block; unanswered; or
unchecked, when the check could not run or the deadline ended it. An ask the
token limit refused sent nothing and leaves that as it was.

Before each pass picks a fork, the tool also asks about each loss site an
input recorded a run of, once per run, in the order recorded, with no stuck
moment, puts a formula that passes both checks in use when it can, and,
after the turn, runs again the input its check used (``pyct.run.call_turns``).
Decision llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it.

``SummaryProvider`` and the ask's request and reply are declared in ``pyct.run.summary_asks``.
"""

from __future__ import annotations

import time
import types
from collections.abc import Callable

from pyct.config.llm import SUMMARIES_TOOL
from pyct.core.foundation.branch import FormulaDrop, Site
from pyct.intercept.model_code import Refused
from pyct.results.causes import SourceKind, WhyEntry
from pyct.results.llm_asks import AskCost, LoopSummary, SummaryState, Unanswered, Why
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.call_turns import NO_RECORDED_RUN, CallTurns
from pyct.run.code_context import code_with_piece
from pyct.run.formula_runner import FormulaText
from pyct.run.loops_in_use import (
    IN_PYCT_S_PROCESS,
    LoopsInUse,
    dropped_because,
    never_used_because,
    place_of,
    unused_because,
)
from pyct.run.model_runs import CANNOT_FORK, can_fork
from pyct.run.notes import (
    AskSkipped,
    ReplyIgnored,
    SummaryChecked,
    SummaryDropped,
    SummaryFailed,
    SummaryNotUsed,
    SummaryRead,
    SummarySkipped,
)
from pyct.run.stuck import Handled, Kind, Moment, Running, going
from pyct.run.summary_asks import (
    EarlierFormula,
    SummaryProvider,
    SummaryReply,
    SummaryRequest,
)
from pyct.run.summary_checks import Ended, check_formula, formula_code
from pyct.run.summary_outcomes import Asked, outcome, sources_of
from pyct.run.summary_outcomes import LoopState as LoopState
from pyct.run.summary_runs import (
    AskedLoop,
    asked_loop,
    failed_run,
    not_shown,
    run_again,
    shown_runs,
)
from pyct.run.summary_runs import ShownRun as ShownRun
from pyct.run.target import Target
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit

# why a loop is not asked about: no run of it holds every name it changes (``NO_RECORDED_RUN``);
# or, as ``CANNOT_FORK`` says, no formula could run beside a second thread of pyct's process
# the states of a loop whose formula is kept: no ask is sent for it
_KEPT = (SummaryState.IN_USE, SummaryState.CHECKED)


class Summaries:
    """The summaries tool for one run: each loop's state, by its site."""

    kind = Kind.SUMMARIES

    def __init__(
        self,
        provider: SummaryProvider,
        target: Target,
        told: Told,
        limit: TokenLimit | None = None,
        *,
        isolated: Callable[[], bool],
    ) -> None:
        self.provider = provider
        self.target = target
        self.told = told
        self.limit = TokenLimit() if limit is None else limit
        # whether the run's inputs run in a process of their own
        self.isolated = isolated
        self.loops: dict[Site, LoopState] = {}
        self.in_use = LoopsInUse()
        # the inputs, by their numbers in the run, that the formulas put in use at this moment were
        # checked on last
        self.again: list[int] = []
        # each loop skipped with no ask, or whose formula is not used, with each reason, said this
        # run
        self.said_once: set[SummarySkipped | SummaryNotUsed] = set()
        # the files the asks read code from, each parsed once this run
        self.files = SourceFiles()
        # the loss sites the inputs recorded runs of, each asked about once per run
        self.calls = CallTurns(self)

    @property
    def can_ask(self) -> bool:
        """Whether summaries may still ask this run: false once the run's token limit is
        reached, by any tool's ask."""
        return not self.limit.reached

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        """Ask once about each loop the entries' sources name, and each dropped loop a line it was
        asked for is still missed for, in code order; ``took``, ``gave up`` or ``skipped`` each
        entry by what came of its sources. A loop an ask was sent for keeps the entries' lines
        that named it. Then run again the inputs the formulas put in use were checked on."""
        named = {each.site for entry in entries for each in sources_of(entry, SourceKind.LOOP)}
        sites = sorted(
            named | set(self._dropped_for(moment)),
            key=lambda site: (site.file, site.line, site.col),
        )
        came: dict[Site, Asked] = {}
        asked = False
        for site in sites:
            if self.limit.reached or not going(moment.run):
                came[site] = Asked.NOT_ASKED
                continue
            came[site], made = self._turn(site, moment.run)
            asked = asked or made
            self._asked_for(site, entries)
        self.run_again(moment.run)
        outcomes = tuple(outcome(entry, came, self.calls.came) for entry in entries)
        return Handled(outcomes, asked)

    def waiting(self, moment: Moment) -> bool:
        """Whether a loop whose formula was dropped waits on this moment: no formula of its is in
        use or checked since, and a line it was asked for is still missed."""
        return bool(self._dropped_for(moment))

    def _dropped_for(self, moment: Moment) -> list[Site]:
        """Each loop whose formula was dropped, with no formula of its in use or checked since,
        that a line it was asked for, still missed at the moment, waits on."""
        missed = {(entry.file, line) for entry in moment.causes for line in entry.lines}
        return [
            site
            for site, state in self.loops.items()
            if state.dropped and state.last not in _KEPT and state.asked_for & missed
        ]

    def _asked_for(self, site: Site, entries: tuple[WhyEntry, ...]) -> None:
        """Keep, with the loop's state once an ask was sent for it, the lines of each entry that
        names it."""
        state = self.loops.get(site)
        if state is None:
            return
        for entry in entries:
            if any(each.site == site for each in sources_of(entry, SourceKind.LOOP)):
                state.asked_for.update((entry.file, line) for line in entry.lines)

    def _turn(self, site: Site, run: Running) -> tuple[Asked, bool]:
        """One loop's turn at this moment, and whether the model was asked."""
        state = self.loops.get(site)
        if state is not None and state.last in _KEPT:
            return Asked.CHECKED, False
        never = never_used_because(site, self.isolated())
        if never is not None:
            self._skipped(site, never)
            return Asked.NEVER_USED, False
        loop = asked_loop(site, run.records)
        if loop is None or not can_fork():
            self._skipped(site, NO_RECORDED_RUN if loop is None else CANNOT_FORK)
            return Asked.NOT_ASKED, False
        state = state or LoopState(loop.piece.changed)
        return self.asked(loop, state, self._request(loop, state), run)

    def between(self, run: Running) -> None:
        """Ask about each loss site an input recorded a run of that had no turn this run, one at
        a time, in the order recorded, until the token limit is reached or the run is no longer
        going (``pyct.run.call_turns``)."""
        self.calls.between(run)

    def asked(
        self, loop: AskedLoop, state: LoopState, request: SummaryRequest, run: Running
    ) -> tuple[Asked, bool]:
        """Send the ask about a loop or a loss site, the clock paused for its wait, and read and
        check its reply; how it ended, and whether the model was asked."""
        started = time.monotonic()
        answer = self.provider.summarize(request)
        run.pause(time.monotonic() - started)
        if isinstance(answer, Unanswered):
            self._unanswered(loop.site, state, answer)
            return Asked.NOT_ASKED, True
        self._sent(loop.site, state, answer.cost)
        if answer.ignored is not None:
            return self._ignored(state, answer.ignored), True
        return self._tried(loop, state, answer, run, request.not_shown), True

    def _ignored(self, state: LoopState, reason: str) -> Asked:
        """A reply that held nothing the tool could read, said; its loop's ask failed."""
        state.last = SummaryState.FAILED
        self.told.note(ReplyIgnored(SUMMARIES_TOOL, reason))
        return Asked.FAILED

    def _skipped(self, site: Site, reason: str) -> None:
        """A loop skipped with no ask, said the first time this run it is skipped for
        ``reason``."""
        self.say_once(SummarySkipped(site, reason))

    def say_once(self, note: SummarySkipped | SummaryNotUsed) -> None:
        """A note said the first time this run it comes, for its loop and reason."""
        if note not in self.said_once:
            self.said_once.add(note)
            self.told.note(note)

    def _tried(
        self,
        loop: AskedLoop,
        state: LoopState,
        reply: SummaryReply,
        run: Running,
        hidden: int,
    ) -> Asked:
        """The reply's formula read, its form checked, then checked on the loop's runs, those
        its request showed and the ``hidden`` it did not, and for values pyct follows: kept when
        it passes, said with ``hidden``, else a failed try, said with its reason.
        A check that could not run, or that the run's deadline ended, leaves the formula
        unchecked and skips the loop at this moment."""
        state.formula = reply.code
        site, piece = loop.site, loop.piece
        file = f"<summary {self.place(site)}>"
        formula = formula_code(reply.code, loop.parameters, piece.changed, file)
        if isinstance(formula, Refused):
            return self._failed(state, site, formula.reason)
        self.told.note(SummaryRead(site, formula.text, formula.below, call=state.name))
        until = run.bounds.until
        failed = check_formula(formula.code, loop.runs, loop.parameters, piece.changed, until)
        if isinstance(failed, Ended):
            state.last = SummaryState.UNCHECKED
            self.told.note(SummarySkipped(site, failed.reason, call=state.name))
            return Asked.NOT_ASKED
        if failed is not None:
            return self._failed(state, site, failed)
        state.checked_on = len(loop.runs)
        self.told.note(SummaryChecked(site, len(loop.runs), hidden, call=state.name))
        if state.name is not None:
            state.last = self.calls.used(loop, state.name, reply.code, file, formula.code)
            return Asked.CHECKED
        state.last = self._used(loop, reply.code, file, formula.code)
        return Asked.CHECKED

    def _used(self, loop: AskedLoop, text: str, file: str, code: types.CodeType) -> SummaryState:
        """A formula that passed both checks, from its text, its code objects' file name and its
        code: in use when it can be, its loop's latest complete run's input kept to run again,
        else kept as checked and said with why."""
        changed = loop.piece.changed
        reason = unused_because(loop.site, loop.runs, changed, self.isolated())
        if reason is not None:
            self.say_once(SummaryNotUsed(loop.site, reason))
            return SummaryState.CHECKED
        formula = FormulaText(text, loop.parameters, changed, place_of(loop.site), file)
        self.in_use.use(formula, code)
        self.again.append(loop.runs[-1].number)
        return SummaryState.IN_USE

    def run_again(self, run: Running) -> None:
        """Run again the inputs the formulas put in use since the last time were checked on, each
        once, in run order, labeled ``summary`` (``pyct.run.summary_runs.run_again``)."""
        again, self.again = self.again, []
        run_again(run, again, self.target)

    def heard(self, record: InputRecord, number: int) -> None:
        """An input the run kept as its input ``number``: each loss site it first recorded a run
        of is noted; each loop in use its record says was dropped goes out of use, said with
        why; then, once the run's inputs run in pyct's own process, each loop and loss site
        still in use goes out of use, kept as checked (``pyct.run.call_turns``)."""
        for drop in record.drops:
            if drop.site in self.in_use.sites:
                self._dropped(drop, record, number)
        self.calls.heard(record, number)
        if not self.in_use.sites or self.isolated():
            return
        for site in sorted(self.in_use.sites, key=lambda site: (site.file, site.line, site.col)):
            self.in_use.stop(site)
            self.loops[site].last = SummaryState.CHECKED
            self.say_once(SummaryNotUsed(site, IN_PYCT_S_PROCESS))

    def _dropped(self, drop: FormulaDrop, record: InputRecord, number: int) -> None:
        """The loop in use the input ``number`` dropped: out of use, said, and its formula kept
        among its earlier tries with why, and the run it failed on, for its next ask."""
        site = drop.site
        self.in_use.stop(site)
        state = self.loops[site]
        state.last = SummaryState.DROPPED
        state.dropped = True
        reason = dropped_because(drop)
        state.tries.append(
            EarlierFormula(state.formula or "", f"dropped at input {number}: {reason}")
        )
        state.failed_on = failed_run(drop, record, number)
        self.told.note(SummaryDropped(site, number, reason))

    def close(self) -> None:
        """The run ends: no loop or loss site of its is in use any more."""
        self.in_use.close()
        self.calls.in_use.close()

    def _failed(self, state: LoopState, site: Site, reason: str) -> Asked:
        """A failed try, said and kept for the loop's later asks."""
        state.last = SummaryState.FAILED
        self.told.note(SummaryFailed(site, state.attempts, reason, call=state.name))
        state.tries.append(EarlierFormula(state.formula or "", reason))
        return Asked.FAILED

    def place(self, site: Site) -> str:
        return f"{self.target.module_of(site.file)}:{site.line}:{site.col}"

    def _request(self, loop: AskedLoop, state: LoopState) -> SummaryRequest:
        site = loop.site
        shown = shown_runs(loop, state.failed_on)
        return SummaryRequest(
            place=self.place(site),
            code=code_with_piece(self.target, site.file, loop.piece.lines, files=self.files),
            parameters=loop.parameters,
            changed=loop.piece.changed,
            runs=shown,
            tries=tuple(state.tries),
            not_shown=not_shown(loop, shown),
        )

    def _unanswered(self, site: Site, state: LoopState, answer: Unanswered) -> None:
        """An ask that got no answer, said and kept for its loop; one the token limit refused
        left no request, and once the limit is reached no tool asks again."""
        if answer.why is Why.LIMIT:
            self.limit.reach()
            return
        self._sent(site, state, answer.cost)
        state.last = SummaryState.UNANSWERED
        self.told.note(AskSkipped(SUMMARIES_TOOL, answer.reason))

    def _sent(self, site: Site, state: LoopState, cost: AskCost) -> None:
        """The loop's state kept once an ask for it was sent, with the connection's try number,
        and no formula checked until its answer is; an answer that leaves no token under the
        limit reaches the run's limit."""
        self.loops[site] = state
        state.attempts = cost.attempt
        state.checked_on = None
        self.limit.heard(cost)

    def states(self) -> tuple[LoopSummary, ...]:
        """Each loop an ask was sent for, in code order, as the summary line lists it, with what
        came of its last ask sent."""
        return tuple(
            LoopSummary(
                site.file,
                site.line,
                site.col,
                state.changes,
                state.formula,
                state.last,
                state.attempts,
                state.checked_on,
                state.kind,
                state.name,
            )
            for site, state in sorted(
                self.loops.items(), key=lambda item: (item[0].file, item[0].line, item[0].col)
            )
        )
