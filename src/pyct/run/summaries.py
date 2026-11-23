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
time this run it is skipped for that reason. An ask that got no answer is said
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

``SummaryProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.summaries``.
Decision llm-summary-provider-declared-in-run.
"""

from __future__ import annotations

import enum
import time
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pyct.config.llm import SUMMARIES_TOOL
from pyct.core.foundation.branch import FormulaDrop, Site
from pyct.intercept.model_code import Refused
from pyct.results.causes import Source, SourceKind, WhyEntry
from pyct.results.llm_asks import AskCost, LoopSummary, SummaryState, Unanswered, Why
from pyct.results.record import InputRecord
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
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Running, going
from pyct.run.summary_checks import CompleteRun, Ended, check_formula, formula_code
from pyct.run.summary_runs import (
    AskedLoop,
    ShownRun,
    asked_loop,
    failed_run,
    not_shown,
    run_again,
    shown_runs,
)
from pyct.run.target import Target
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit

# why a loop is not asked about: no run of it holds every name it changes; or, as
# ``CANNOT_FORK`` says, no formula could run beside a second thread of pyct's process
NO_RECORDED_RUN = "no recorded run"
# the states of a loop whose formula is kept: no ask is sent for it
_KEPT = (SummaryState.IN_USE, SummaryState.CHECKED)


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
    are the formula's parameters, the names going in that every complete run holds;
    ``changed`` the names the loop changes; ``runs`` the runs shown; ``tries`` the earlier
    tries at this place, oldest first; ``not_shown`` the complete runs whose values going in no
    shown run has.
    """

    place: str
    code: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    runs: tuple[ShownRun, ...]
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
    """Gives a loop's summary. It never raises for an LLM problem: it returns Unanswered."""

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered: ...


class Asked(enum.Enum):
    """How one loop's turn at a moment ended."""

    CHECKED = enum.auto()
    FAILED = enum.auto()
    NOT_ASKED = enum.auto()


@dataclass
class LoopState:
    """One loop an ask was sent for, across the run: the names it changes, the connection's last
    try number, the earlier tries that failed or were dropped, the last formula the model gave,
    the runs a formula was checked on once one is checked, what came of the last ask sent for
    it, unanswered until its answer is read, the run its last formula was dropped on, whether a
    formula of its was ever dropped, and the lines it was asked for. An ask the token limit
    refused sent nothing and changes none of these."""

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
        named = {each.site for entry in entries for each in _sources(entry, SourceKind.LOOP)}
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
        again, self.again = self.again, []
        run_again(moment.run, again, self.target)
        return Handled(tuple(_outcome(entry, came) for entry in entries), asked)

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
            if any(each.site == site for each in _sources(entry, SourceKind.LOOP)):
                state.asked_for.update((entry.file, line) for line in entry.lines)

    def _turn(self, site: Site, run: Running) -> tuple[Asked, bool]:
        """One loop's turn at this moment, and whether the model was asked."""
        state = self.loops.get(site)
        if state is not None and state.last in _KEPT:
            return Asked.CHECKED, False
        never = never_used_because(site, self.isolated())
        if never is not None:
            self._skipped(site, never)
            return Asked.NOT_ASKED, False
        loop = asked_loop(site, run.records)
        if loop is None or not can_fork():
            self._skipped(site, NO_RECORDED_RUN if loop is None else CANNOT_FORK)
            return Asked.NOT_ASKED, False
        state = state or LoopState(loop.piece.changed)
        request = self._request(loop, state)
        started = time.monotonic()
        answer = self.provider.summarize(request)
        run.pause(time.monotonic() - started)
        if isinstance(answer, Unanswered):
            self._unanswered(site, state, answer)
            return Asked.NOT_ASKED, True
        self._sent(site, state, answer.cost)
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
        self._say_once(SummarySkipped(site, reason))

    def _say_once(self, note: SummarySkipped | SummaryNotUsed) -> None:
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
        file = f"<summary {self._place(site)}>"
        formula = formula_code(reply.code, loop.parameters, piece.changed, file)
        if isinstance(formula, Refused):
            return self._failed(state, site, formula.reason)
        self.told.note(SummaryRead(site, formula.text, formula.below))
        until = run.bounds.until
        failed = check_formula(formula.code, loop.runs, loop.parameters, piece.changed, until)
        if isinstance(failed, Ended):
            state.last = SummaryState.UNCHECKED
            self.told.note(SummarySkipped(site, failed.reason))
            return Asked.NOT_ASKED
        if failed is not None:
            return self._failed(state, site, failed)
        state.checked_on = len(loop.runs)
        self.told.note(SummaryChecked(site, len(loop.runs), hidden))
        state.last = self._used(loop, reply.code, file, formula.code)
        return Asked.CHECKED

    def _used(self, loop: AskedLoop, text: str, file: str, code: types.CodeType) -> SummaryState:
        """A formula that passed both checks, from its text, its code objects' file name and its
        code: in use when it can be, its loop's latest complete run's input kept to run again,
        else kept as checked and said with why."""
        changed = loop.piece.changed
        reason = unused_because(loop.site, loop.runs, changed, self.isolated())
        if reason is not None:
            self._say_once(SummaryNotUsed(loop.site, reason))
            return SummaryState.CHECKED
        formula = FormulaText(text, loop.parameters, changed, place_of(loop.site), file)
        self.in_use.use(formula, code)
        self.again.append(loop.runs[-1].number)
        return SummaryState.IN_USE

    def heard(self, record: InputRecord, number: int) -> None:
        """An input the run kept as its input ``number``: each loop in use its record says was
        dropped goes out of use, said with why; then, once the run's inputs run in pyct's own
        process, each loop still in use goes out of use, kept as checked."""
        for drop in record.drops:
            if drop.site in self.in_use.sites:
                self._dropped(drop, record, number)
        if not self.in_use.sites or self.isolated():
            return
        for site in sorted(self.in_use.sites, key=lambda site: (site.file, site.line, site.col)):
            self.in_use.stop(site)
            self.loops[site].last = SummaryState.CHECKED
            self._say_once(SummaryNotUsed(site, IN_PYCT_S_PROCESS))

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
        """The run ends: no loop of its is in use any more."""
        self.in_use.close()

    def _failed(self, state: LoopState, site: Site, reason: str) -> Asked:
        """A failed try, said and kept for the loop's later asks."""
        state.last = SummaryState.FAILED
        self.told.note(SummaryFailed(site, state.attempts, reason))
        state.tries.append(EarlierFormula(state.formula or "", reason))
        return Asked.FAILED

    def _place(self, site: Site) -> str:
        return f"{self.target.module_of(site.file)}:{site.line}:{site.col}"

    def _request(self, loop: AskedLoop, state: LoopState) -> SummaryRequest:
        site = loop.site
        shown = shown_runs(loop, state.failed_on)
        return SummaryRequest(
            place=self._place(site),
            code=code_with_piece(self.target, site.file, loop.piece.lines),
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
            )
            for site, state in sorted(
                self.loops.items(), key=lambda item: (item[0].file, item[0].line, item[0].col)
            )
        )


def _sources(entry: WhyEntry, kind: SourceKind) -> list[Source]:
    return [each for each in entry.sources or () if each.kind is kind]


def _outcome(entry: WhyEntry, came: dict[Site, Asked]) -> Outcome:
    """``took`` when each loop the entry names has a checked formula; ``gave up`` when a try at
    one failed or its reply was ignored, or when the entry names a call; ``skipped`` else."""
    loops = [came[each.site] for each in _sources(entry, SourceKind.LOOP)]
    calls = _sources(entry, SourceKind.LOST)
    if loops and not calls and all(each is Asked.CHECKED for each in loops):
        return Outcome.TOOK
    if calls or Asked.FAILED in loops:
        return Outcome.GAVE_UP
    return Outcome.SKIPPED
