"""The summaries tool in a run: the stuck moment's summaries slot, what a summaries ask is about
and gives back, and the provider that answers it.

Before each pass picks a fork, the tool asks about each loss site an input
recorded a run of, once per run, in the order recorded, with no stuck
moment, puts a formula that passes both checks in use when it can, and,
after the turn, runs again the input its check used (``pyct.run.call_turns``).
Decision llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it.
At a stuck moment it asks nothing: it takes each ``no fork`` entry and hands
back what came of the loss sites the entry names (``pyct.run.summary_outcomes``).
An ask that got no answer is said; once an answer leaves no token under the
limit no summary is asked for again this run, the tool says it can ask no
more, and the connection has said so. A reply with no code block is said.
The wait for the model pauses the run's clock.

A reply's formula is read, checked for its form, then checked on the site's
complete runs and for values pyct follows (``pyct.run.summary_checks``). A
formula that fails a check is a failed try, said with its reason and kept for
the site's later asks; one that passes both is kept for its site, and comes
into use from the next input on when it can (``pyct.run.call_turns``). A check
whose child could not start, or that the run's deadline ended, is no try: the
site is skipped at this turn, and said.

The summary line lists each loss site an ask was sent for with what came of
its last ask sent (``SummaryState``): its formula in use, checked and not
used, or dropped; failed, by a check or a reply with no code block;
unanswered; or unchecked, when the check could not run or the deadline ended
it. An ask the token limit refused sent nothing and leaves that as it was.

``SummaryProvider`` and the ask's request and reply are declared in ``pyct.run.summary_asks``.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from pyct.config.llm import SUMMARIES_TOOL
from pyct.core.foundation.branch import Site
from pyct.intercept.model_code import Refused
from pyct.results.causes import WhyEntry
from pyct.results.llm_asks import AskCost, SiteSummary, SummaryState, Unanswered, Why
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.call_summaries import CHANGED, AskedCall
from pyct.run.call_turns import CallTurns
from pyct.run.notes import (
    AskSkipped,
    ReplyIgnored,
    SummaryChecked,
    SummaryFailed,
    SummaryNotUsed,
    SummaryRead,
    SummarySkipped,
)
from pyct.run.stuck import Handled, Kind, Moment, Running
from pyct.run.summary_asks import (
    EarlierFormula,
    SummaryProvider,
    SummaryReply,
    SummaryRequest,
)
from pyct.run.summary_checks import Ended, check_formula, formula_code
from pyct.run.summary_outcomes import Asked, SiteState, outcome
from pyct.run.summary_runs import ShownRun as ShownRun
from pyct.run.summary_runs import run_again
from pyct.run.target import Target
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit


class Summaries:
    """The summaries tool for one run: each loss site's state, by its site."""

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
        self.sites: dict[Site, SiteState] = {}
        # the inputs, by their numbers in the run, that the formulas put in use at this turn were
        # checked on last
        self.again: list[int] = []
        # each loss site skipped with no ask, or whose formula is not used, with each reason, said
        # this run
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
        """Ask nothing; ``took``, ``gave up`` or ``skipped`` each entry by what came of the loss
        sites it names (``pyct.run.summary_outcomes.outcome``)."""
        return Handled(tuple(outcome(entry, self.calls.came) for entry in entries), asked=False)

    def waiting(self, moment: Moment) -> bool:
        """No loss site waits on a moment: each is asked about between passes."""
        return False

    def between(self, run: Running) -> None:
        """Ask about each loss site an input recorded a run of that had no turn this run, one at
        a time, in the order recorded, until the token limit is reached or the run is no longer
        going (``pyct.run.call_turns``)."""
        self.calls.between(run)

    def asked(
        self, call: AskedCall, state: SiteState, request: SummaryRequest, run: Running
    ) -> tuple[Asked, bool]:
        """Send the ask about a loss site, the clock paused for its wait, and read and check its
        reply; how it ended, and whether the model was asked."""
        started = time.monotonic()
        answer = self.provider.summarize(request)
        run.pause(time.monotonic() - started)
        if isinstance(answer, Unanswered):
            self._unanswered(call.site, state, answer)
            return Asked.NOT_ASKED, True
        self._sent(call.site, state, answer.cost)
        if answer.ignored is not None:
            return self._ignored(state, answer.ignored), True
        return self._tried(call, state, answer, run, request.not_shown), True

    def _ignored(self, state: SiteState, reason: str) -> Asked:
        """A reply that held nothing the tool could read, said; its site's ask failed."""
        state.last = SummaryState.FAILED
        self.told.note(ReplyIgnored(SUMMARIES_TOOL, reason))
        return Asked.FAILED

    def say_once(self, note: SummarySkipped | SummaryNotUsed) -> None:
        """A note said the first time this run it comes, for its loss site and reason."""
        if note not in self.said_once:
            self.said_once.add(note)
            self.told.note(note)

    def _tried(
        self,
        call: AskedCall,
        state: SiteState,
        reply: SummaryReply,
        run: Running,
        hidden: int,
    ) -> Asked:
        """The reply's formula read, its form checked, then checked on the site's runs, those
        its request showed and the ``hidden`` it did not, and for values pyct follows: kept when
        it passes, said with ``hidden``, else a failed try, said with its reason.
        A check that could not run, or that the run's deadline ended, leaves the formula
        unchecked and skips the site at this turn."""
        state.formula = reply.code
        site = call.site
        file = f"<summary {self.place(site)}>"
        formula = formula_code(reply.code, call.parameters, CHANGED, file)
        if isinstance(formula, Refused):
            return self._failed(state, site, formula.reason)
        self.told.note(SummaryRead(site, formula.text, formula.below, call=state.name))
        until = run.bounds.until
        failed = check_formula(formula.code, call.runs, call.parameters, CHANGED, until)
        if isinstance(failed, Ended):
            state.last = SummaryState.UNCHECKED
            self.told.note(SummarySkipped(site, failed.reason, call=state.name))
            return Asked.NOT_ASKED
        if failed is not None:
            return self._failed(state, site, failed)
        state.checked_on = len(call.runs)
        self.told.note(SummaryChecked(site, len(call.runs), hidden, call=state.name))
        state.last = self.calls.used(call, reply.code, file, formula.code)
        return Asked.CHECKED

    def run_again(self, run: Running) -> None:
        """Run again the inputs the formulas put in use since the last time were checked on, each
        once, in run order, labeled ``summary`` (``pyct.run.summary_runs.run_again``). With none
        waiting, as at most passes, it reads nothing."""
        if not self.again:
            return
        again, self.again = self.again, []
        run_again(run, again, self.target)

    def heard(self, record: InputRecord, number: int) -> None:
        """An input the run kept as its input ``number``, which the loss sites' turns hear
        (``pyct.run.call_turns``)."""
        self.calls.heard(record, number)

    def close(self) -> None:
        """The run ends: no loss site of its is in use any more."""
        self.calls.in_use.close()

    def _failed(self, state: SiteState, site: Site, reason: str) -> Asked:
        """A failed try, said and kept for the site's later asks."""
        state.last = SummaryState.FAILED
        self.told.note(SummaryFailed(site, state.attempts, reason, call=state.name))
        state.tries.append(EarlierFormula(state.formula or "", reason))
        return Asked.FAILED

    def place(self, site: Site) -> str:
        return f"{self.target.module_of(site.file)}:{site.line}:{site.col}"

    def _unanswered(self, site: Site, state: SiteState, answer: Unanswered) -> None:
        """An ask that got no answer, said and kept for its site; one the token limit refused
        left no request, and once the limit is reached no tool asks again."""
        if answer.why is Why.LIMIT:
            self.limit.reach()
            return
        self._sent(site, state, answer.cost)
        state.last = SummaryState.UNANSWERED
        self.told.note(AskSkipped(SUMMARIES_TOOL, answer.reason))

    def _sent(self, site: Site, state: SiteState, cost: AskCost) -> None:
        """The site's state kept once an ask for it was sent, with the connection's try number,
        and no formula checked until its answer is; an answer that leaves no token under the
        limit reaches the run's limit."""
        self.sites[site] = state
        state.attempts = cost.attempt
        state.checked_on = None
        self.limit.heard(cost)

    def states(self) -> tuple[SiteSummary, ...]:
        """Each loss site an ask was sent for, in code order, as the summary line lists it, with
        what came of its last ask sent."""
        return tuple(
            SiteSummary(
                state.name,
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
                self.sites.items(), key=lambda item: (item[0].file, item[0].line, item[0].col)
            )
        )
