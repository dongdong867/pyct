"""The guesses tool in a run: the stuck moment's last slot, after summaries and rewrites.

At a moment, guesses take every entry the moment hands them (``pyct.run.stuck``) and make one
ask about all of them, said before it goes out. Each entry is asked about with its cause, the
conditions on the way to its first line with the side the line needs, and the input that got
furthest along that way with how it ended (``pyct.results.furthest``), worked out within
``WAY_SECONDS`` and the run's deadline. The request also holds the target's code, its signature
and the classes of its folder, as the seeds ask does. The wait for the model pauses the run's
clock. An ask that got no answer is said; once any tool's reply leaves no token under the limit,
or an ask meets it, no guess is asked for again this run (``pyct.run.token_limit``), and the
connection has said so.

The reply's guesses are judged and run in reply order, at most ``MOST_GUESSES``. Each is read
and checked as an LLM seed is (``checked_seed``), filled with the simple defaults it leaves out
(``with_defaults``), then dropped when it writes the same JSON as an input that ran, an earlier
guess's included. Each drop is said with its reason. A guess that passes runs between two passes
as ``"source": "guess"``, its path joining the tree, and a guess that covered lines the ask was
about says which. Once the budget is spent or an input met the run's stop, no later guess is
judged, run or said.

An entry is ``took`` when a guess covered one of its lines, ``gave up`` when the ask was
answered and no guess did, and ``skipped`` when the ask got no answer or none was made.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Mapping, Sequence

from pyct.binding.bind import Seed
from pyct.results.causes import Reason, WhyEntry
from pyct.results.furthest import way_to
from pyct.results.graphs import LONGEST_STRETCH
from pyct.results.llm_asks import Unanswered, Why
from pyct.results.record import InputRecord, Source, Stop
from pyct.rewrite.provider import Side
from pyct.rewrite.request import condition_text
from pyct.run.class_listing import ClassListing, class_listing
from pyct.run.code_context import code_context
from pyct.run.defaults import with_defaults
from pyct.run.guess_asks import AskedLine, GuessProvider, GuessRequest
from pyct.run.llm_seeds import ClassGate, checked_seed, seed_json
from pyct.run.notes import (
    AskedFor,
    AskSkipped,
    GuessDropped,
    GuessesAsked,
    GuessReached,
    ReplyIgnored,
)
from pyct.run.seed_checks import SeedCheck
from pyct.run.stuck import CAUSE_SECONDS, Handled, Kind, Moment, Outcome, Running, going
from pyct.run.target import Target, argument_checks
from pyct.run.tell import Told
from pyct.run.token_limit import TokenLimit

# the most guesses of one reply that are judged and run
MOST_GUESSES = 5
# the characters of JSON the furthest input may take in a request
FURTHEST_SIZE = 2_000
# how long one ask works out the ways to its lines, at most, as a moment works out causes
WAY_SECONDS = CAUSE_SECONDS
# why a reply whose array is empty gives no guess
NO_GUESS = "the reply held no guess"
# the tool's name, as stderr writes it
_NAME = Kind.GUESSES.value


class Guesses:
    """The guesses tool for one run: its asks' count, and which of the tools before it are
    switched on, which says what an entry they would have taken came to."""

    kind = Kind.GUESSES

    def __init__(
        self,
        provider: GuessProvider,
        target: Target,
        told: Told,
        limit: TokenLimit,
        others: frozenset[Kind],
    ) -> None:
        self.provider = provider
        self.target = target
        self.told = told
        self.limit = limit
        self.others = others
        self.asks = 0

    @property
    def can_ask(self) -> bool:
        """Whether guesses may still ask this run: false once the run's token limit is reached,
        by any tool's ask."""
        return not self.limit.reached

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        """Ask once about every entry, then judge and run the reply's guesses."""
        run = moment.run
        if self.limit.reached or not going(run):
            return _all(entries, Outcome.SKIPPED, asked=False)
        causes = tuple(AskedFor(each.file, each.lines, self._cause(each)) for each in entries)
        self.told.note(GuessesAsked(causes))
        request = self._request(entries, causes, run)
        started = time.monotonic()
        answer = self.provider.guesses(request)
        run.pause(time.monotonic() - started)
        self.limit.heard(answer.cost)
        if isinstance(answer, Unanswered):
            if answer.why is Why.LIMIT:
                self.limit.reach()
            else:
                self.told.note(AskSkipped(_NAME, answer.reason))
            return _all(entries, Outcome.SKIPPED, asked=True)
        if answer.ignored is not None or not answer.items:
            self.told.note(ReplyIgnored(_NAME, answer.ignored or NO_GUESS))
            return _all(entries, Outcome.GAVE_UP, asked=True)
        reached = self._run_each(answer.items, entries, run)
        outcomes = tuple(
            Outcome.TOOK if reached & set(each.lines) else Outcome.GAVE_UP for each in entries
        )
        return Handled(outcomes, True)

    def heard(self, record: InputRecord, number: int) -> None:
        """Each input the run keeps: guesses read the run's inputs at each ask instead."""

    def waiting(self, moment: Moment) -> bool:
        """Guesses ask at a moment only about the entries they are handed."""
        return False

    @functools.cached_property
    def _listing(self) -> ClassListing:
        return class_listing(self.target.spec.partition("::")[0])

    @functools.cached_property
    def _code(self) -> str:
        return code_context(self.target)

    @functools.cached_property
    def _check(self) -> SeedCheck:
        return SeedCheck.of(self.target)

    def _cause(self, entry: WhyEntry) -> str:
        """The entry's cause in the request's words: the tool before guesses that gave up on
        it when that tool is on, else the cause's own word, a ``no fork`` with no source found
        saying so."""
        if entry.reason is Reason.NO_FORK:
            if Kind.SUMMARIES in self.others:
                return "summary gave up"
            return "no fork, no source found" if entry.sources == () else "no fork"
        if entry.reason is Reason.NOT_TAKEN and Kind.REWRITES in self.others:
            return "rewrite gave up"
        return entry.reason.value

    def _request(
        self,
        entries: tuple[WhyEntry, ...],
        causes: tuple[AskedFor, ...],
        run: Running,
    ) -> GuessRequest:
        """The request for this ask, each entry's way worked out by one stop for them all."""
        self.asks += 1
        stop_at = _way_stop(run.bounds.until)
        target = self.target
        lines = tuple(
            self._asked(entry, cause.cause, run.records, stop_at)
            for entry, cause in zip(entries, causes, strict=True)
        )
        return GuessRequest(
            place=f"{target.spec}#{self.asks}",
            code=self._code,
            signature=str(target.signature),
            lines=lines,
            classes=self._listing.text,
        )

    def _asked(
        self, entry: WhyEntry, cause: str, records: Sequence[InputRecord], stop_at: float
    ) -> AskedLine:
        """One entry as the request names it, its file by its module."""
        way = way_to(entry.file, entry.lines[0], records, stop_at)
        module_of = self.target.module_of
        conditions = tuple(
            Side(condition_text(each.site, module_of(each.site.file)), each.side)
            for each in way.conditions
        )
        asked = AskedLine(module_of(entry.file), entry.lines, cause, conditions)
        if way.furthest is None:
            return asked
        furthest = records[way.furthest - 1]
        written = seed_json(furthest.args)
        if written is None:
            return asked
        return AskedLine(
            asked.module, asked.lines, cause, conditions, written[:FURTHEST_SIZE], _ended(furthest)
        )

    def _run_each(
        self, items: tuple[str, ...], entries: tuple[WhyEntry, ...], run: Running
    ) -> set[int]:
        """Judge and run each guess in turn; the lines the ask was about that they covered."""
        inputs: dict[str, int] = {}
        for number, record in enumerate(run.records, start=1):
            _known(inputs, record.args, number)
        about = sorted({(each.file, line) for each in entries for line in each.lines})
        reached: set[int] = set()
        for number, text in enumerate(items, start=1):
            if not going(run):
                break
            seed = self._judged(number, text, inputs)
            if seed is None:
                continue
            ran = run.run_input(seed, Source.GUESS)
            if isinstance(ran, Stop):
                break
            _known(inputs, ran.args, len(run.records))
            covered = tuple(each for each in about if each[1] in ran.covered_lines)
            if covered:
                self.told.note(GuessReached(number, covered))
                reached.update(line for _, line in covered)
        return reached

    def _judged(self, number: int, text: str, inputs: dict[str, int]) -> Seed | None:
        """The input the guess at ``number`` gives, or None when it is dropped, said with why:
        past ``MOST_GUESSES``, by ``checked_seed``, or as the same input as one that ran."""
        if number > MOST_GUESSES:
            return self._dropped(number, f"more than {MOST_GUESSES} guesses")
        target = self.target
        gate = ClassGate(target.home, self._listing.modules)
        reason, checked = checked_seed(self._check, gate, text)
        if checked is None:
            return self._dropped(number, reason)
        seed = Seed.of(with_defaults(target, checked), argument_checks(target), target.home)
        written = seed_json(seed.args)
        repeated = None if written is None else inputs.get(written)
        if repeated is not None:
            return self._dropped(number, f"same input as input {repeated}")
        return seed

    def _dropped(self, number: int, reason: str) -> None:
        self.told.note(GuessDropped(number, reason))


def _all(entries: tuple[WhyEntry, ...], outcome: Outcome, *, asked: bool) -> Handled:
    return Handled((outcome,) * len(entries), asked)


def _known(inputs: dict[str, int], args: Mapping[str, object], number: int) -> None:
    """Keep the input ``number``'s JSON, unless an earlier input wrote the same or JSON cannot
    write it."""
    written = seed_json(args)
    if written is not None:
        inputs.setdefault(written, number)


def _ended(record: InputRecord) -> str:
    """How an input ended: ``returned``, or its failure's kind and detail."""
    failure = record.failure
    return "returned" if failure is None else f"{failure.kind.value}: {failure.detail}"


def _way_stop(until: float | None) -> float:
    """When an ask starting now stops working out ways: ``WAY_SECONDS`` from now, or the run's
    deadline when it comes first, less the stretch the analysis may see its stop late."""
    stop = time.monotonic() + WAY_SECONDS
    if until is not None:
        stop = min(stop, until)
    return stop - LONGEST_STRETCH
