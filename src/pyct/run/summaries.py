"""The summaries tool in a run: the stuck moment's summaries slot, what a summaries ask is about
and gives back, and the provider that answers it.

At a moment, summaries take each ``no fork`` entry, and ask once about each
distinct loop its sources name, in code order, however many entries name it.
A loop is asked about with its function's code, the loop marked, and its
complete runs: the runs of it the inputs so far recorded that hold every
name it changes, up to 3 per input. A loop with no complete run, and one
asked about while pyct's process runs a second thread, so that no formula
could run, is skipped at this moment with no ask, and said. An ask that got
no answer is said and ends that loop's tries at this moment; once the token
limit is reached no summary is asked for again this run, and the connection
has said so. A reply with no code block is said and ends them too. The wait
for the model pauses the run's clock. A call a cause names gets no ask.

A reply's formula is read, checked for its form, then checked on the
loop's complete runs and for values pyct follows (``pyct.run.summary_checks``).
A formula that fails a check is a failed try, said with its reason and kept
for the loop's later asks; one that passes both is kept for its loop as
checked, and that loop is not asked about again. No input runs and nothing
is rebound.

``SummaryProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.summaries``.
Decision llm-summary-provider-declared-in-run.
"""

from __future__ import annotations

import ast
import enum
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pyct.config.llm import SUMMARIES_TOOL
from pyct.core.foundation.branch import PieceRun, Site
from pyct.intercept.model_code import Refused
from pyct.results.causes import Source, SourceKind, WhyEntry
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.pieces import FUNCTIONS, Piece, pieces
from pyct.results.record import InputRecord
from pyct.run.code_context import code_with_piece
from pyct.run.model_runs import can_fork
from pyct.run.notes import (
    AskSkipped,
    ReplyIgnored,
    SummaryChecked,
    SummaryFailed,
    SummaryRead,
    SummarySkipped,
)
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Running, going
from pyct.run.summary_checks import CompleteRun, Ended, check_formula, formula_code
from pyct.run.target import Target
from pyct.run.tell import Told

# the recorded runs a request shows at most
SHOWN_RUNS = 10
# why a loop is not asked about: no run of it holds every name it changes, or no formula could
# run beside a second thread of pyct's process
NO_RECORDED_RUN = "no recorded run"
CANNOT_FORK = "cannot fork"


@dataclass(frozen=True)
class ShownRun:
    """One recorded run of the loop as a request shows it: each parameter with its value at the
    start, and each changed name with its value at the end, each value JSON text."""

    going_in: tuple[tuple[str, str], ...]
    changed: tuple[tuple[str, str], ...]


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
    tries at this place, oldest first.
    """

    place: str
    code: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    runs: tuple[ShownRun, ...]
    tries: tuple[EarlierFormula, ...] = ()


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


@dataclass(frozen=True)
class AskedLoop:
    """A loop at one moment: its site, its piece, its complete runs, and the formula's
    parameters."""

    site: Site
    piece: Piece
    runs: tuple[CompleteRun, ...]
    parameters: tuple[str, ...]


class Asked(enum.Enum):
    """How one loop's turn at a moment ended."""

    CHECKED = enum.auto()
    FAILED = enum.auto()
    NOT_ASKED = enum.auto()


@dataclass
class LoopState:
    """One loop across the run: the connection's last try number, the earlier tries that
    failed, the last formula the model gave, and, once one is checked, the runs it was checked
    on."""

    attempts: int = 0
    tries: list[EarlierFormula] = field(default_factory=list)
    formula: str | None = None
    checked_on: int | None = None


class Summaries:
    """The summaries tool for one run: each loop's state, by its site."""

    kind = Kind.SUMMARIES

    def __init__(self, provider: SummaryProvider, target: Target, told: Told) -> None:
        self.provider = provider
        self.target = target
        self.told = told
        self.loops: dict[Site, LoopState] = {}
        self._limit_reached = False

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        """Ask once about each loop the entries' sources name, in code order; ``took``, ``gave
        up`` or ``skipped`` each entry by what came of its sources."""
        sites = sorted(
            {each.site for entry in entries for each in _sources(entry, SourceKind.LOOP)},
            key=lambda site: (site.file, site.line, site.col),
        )
        came: dict[Site, Asked] = {}
        asked = False
        for site in sites:
            if self._limit_reached or not going(moment.run):
                came[site] = Asked.NOT_ASKED
                continue
            came[site], made = self._turn(site, moment.run)
            asked = asked or made
        return Handled(tuple(_outcome(entry, came) for entry in entries), asked)

    def _turn(self, site: Site, run: Running) -> tuple[Asked, bool]:
        """One loop's turn at this moment, and whether the model was asked."""
        state = self.loops.get(site)
        if state is not None and state.checked_on is not None:
            return Asked.CHECKED, False
        loop = asked_loop(site, run.records)
        if loop is None or not can_fork():
            self.told.note(SummarySkipped(site, NO_RECORDED_RUN if loop is None else CANNOT_FORK))
            return Asked.NOT_ASKED, False
        state = self.loops.setdefault(site, LoopState())
        started = time.monotonic()
        answer = self.provider.summarize(self._request(loop, state))
        run.pause(time.monotonic() - started)
        if isinstance(answer, Unanswered):
            self._unanswered(answer)
            return Asked.NOT_ASKED, True
        state.attempts = answer.cost.attempt
        if answer.ignored is not None:
            self.told.note(ReplyIgnored(SUMMARIES_TOOL, answer.ignored))
            return Asked.FAILED, True
        return self._tried(loop, state, answer, run), True

    def _tried(self, loop: AskedLoop, state: LoopState, reply: SummaryReply, run: Running) -> Asked:
        """The reply's formula read, its form checked, then checked on the loop's runs and
        for values pyct follows: kept when it passes, else a failed try, said with its reason.
        A check that could not run skips the loop at this moment."""
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
            self.told.note(SummarySkipped(site, failed.reason))
            return Asked.NOT_ASKED
        if failed is not None:
            return self._failed(state, site, failed)
        state.checked_on = len(loop.runs)
        self.told.note(SummaryChecked(site, len(loop.runs)))
        return Asked.CHECKED

    def _failed(self, state: LoopState, site: Site, reason: str) -> Asked:
        """A failed try, said and kept for the loop's later asks."""
        self.told.note(SummaryFailed(site, state.attempts, reason))
        state.tries.append(EarlierFormula(state.formula or "", reason))
        return Asked.FAILED

    def _place(self, site: Site) -> str:
        return f"{self.target.module_of(site.file)}:{site.line}:{site.col}"

    def _request(self, loop: AskedLoop, state: LoopState) -> SummaryRequest:
        site = loop.site
        return SummaryRequest(
            place=self._place(site),
            code=code_with_piece(self.target, site.file, loop.piece.lines),
            parameters=loop.parameters,
            changed=loop.piece.changed,
            runs=shown_runs(loop),
            tries=tuple(state.tries),
        )

    def _unanswered(self, answer: Unanswered) -> None:
        """An ask that got no answer, said; once the token limit is reached, no loop asks
        again."""
        if answer.why is Why.LIMIT:
            self._limit_reached = True
        else:
            self.told.note(AskSkipped(SUMMARIES_TOOL, answer.reason))


def asked_loop(site: Site, records: Sequence[InputRecord]) -> AskedLoop | None:
    """The loop at ``site`` with its complete runs in the records, oldest first, and the names
    going in that each holds; None when the site holds no piece or no run is complete."""
    piece = piece_at(site)
    if piece is None:
        return None
    wanted = set(piece.changed)
    runs = tuple(
        CompleteRun(number, each)
        for number, record in enumerate(records, start=1)
        for each in record.pieces
        if each.site == site and wanted <= {changed.name for changed in each.changed}
    )
    if not runs:
        return None
    held = [{going.name for going in each.run.going_in} for each in runs]
    parameters = tuple(name for name in piece.going_in if all(name in names for names in held))
    return AskedLoop(site, piece, runs, parameters)


def shown_runs(loop: AskedLoop) -> tuple[ShownRun, ...]:
    """Up to ``SHOWN_RUNS`` of the loop's complete runs, as values: those whose values going in
    differ from every earlier one's first, then those whose changed values differ, then the
    rest, each group in run order."""
    every = [_shown(each.run, loop) for each in loop.runs]
    picked: list[int] = []
    for part in ("going_in", "changed"):
        seen = {getattr(every[at], part) for at in picked}
        for at, each in enumerate(every):
            if at not in picked and getattr(each, part) not in seen:
                seen.add(getattr(each, part))
                picked.append(at)
    picked += [at for at in range(len(every)) if at not in picked]
    return tuple(every[at] for at in picked[:SHOWN_RUNS])


def _shown(run: PieceRun, loop: AskedLoop) -> ShownRun:
    going_in = tuple((each.name, each.value) for each in run.going_in)
    changed = {each.name: each.value for each in run.changed}
    return ShownRun(
        tuple(pair for pair in going_in if pair[0] in loop.parameters),
        tuple((name, changed[name]) for name in loop.piece.changed),
    )


def piece_at(site: Site) -> Piece | None:
    """The piece of a function in ``site``'s file at its line and column, as the file reads now;
    None when it does not read or parse, or holds none there."""
    try:
        with open(site.file, encoding="utf-8") as opened:
            tree = ast.parse(opened.read(), filename=site.file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, FUNCTIONS):
            for _, piece in pieces(node):
                if (piece.line, piece.col) == (site.line, site.col):
                    return piece
    return None


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
