"""One input's record, and the result of one run."""

import dataclasses
import functools
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from pyct.core.branch import Branch, ForkSite, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.graphs import LONGEST_STRETCH
from pyct.results.why import Run, Tries, Walked, WhyEntry, explain

# how long past a run's deadline pyct goes on working out why lines were missed
ANALYSIS_GRACE = 0.5


class Source(StrEnum):
    """Where an input came from. The values are the words on the line."""

    SEED = "seed"
    SOLVER = "solver"


@dataclass(frozen=True)
class Aim:
    """The fork an input was solved for: where it is, and where on the path.

    ``raising`` says the fork is an operation's before a raise (``Branch.raising``).
    """

    site: Site
    position: int
    raising: bool = False


@dataclass(frozen=True)
class DowngradeCount:
    """A run of consecutive calls of one method or dunder, at one site, that dropped the condition.

    ``site`` is where the calls were made, found as a fork's site is.
    """

    name: str
    count: int
    site: Site


@dataclass(frozen=True)
class InputRecord:
    """What one input did: its arguments, the forks it took, the lines it reached.

    ``failure`` is how it ended when it did not return. ``downgrades`` names
    each call that dropped the condition, in order, a run of one method or
    dunder at one site counted as a single entry.

    ``aim`` is the fork the solver was asked for, and ``mismatch_at`` the
    first position where the run left that plan. A seed is aimed at nothing,
    so both stay ``None``.
    """

    args: Mapping[str, object]
    forks: tuple[Branch, ...]
    covered_lines: frozenset[int]
    failure: Failure | None = None
    downgrades: tuple[DowngradeCount, ...] = ()
    source: Source = Source.SEED
    aim: Aim | None = None
    mismatch_at: int | None = None


class StopKind(StrEnum):
    """Why a run ended. ``Stop.reason`` turns a kind into the words on the
    ``stopped`` line, adding the N a plateau stop names."""

    # the pool has no open fork left: every fork of every path was aimed at, or
    # both its sides ran
    NO_FORK = "no fork to flip"
    BUDGET = "budget spent"
    NO_GAIN = "no gain"
    SOLVER_FAILED = "solver failed"
    # pyct could not start a process for an input; the detail is the system's reason
    COULD_NOT_START = "could not start an input"


@dataclass(frozen=True)
class Stop:
    """How the run ended: what went wrong when something did, and the plateau it ran out of.

    ``reason`` is the words both the stderr line and the summary line carry,
    which is the kind's own for every stop but a no-gain one.
    """

    kind: StopKind
    detail: str | None = None
    plateau: int | None = None

    def __post_init__(self) -> None:
        if self.kind is StopKind.NO_GAIN and self.plateau is None:
            raise ValueError("a no-gain stop names its plateau")

    @property
    def reason(self) -> str:
        """Why the run ended, in the words the ``stopped`` line carries.

        One source for the summary line and the stderr line, so the two
        streams cannot drift apart.
        """
        if self.kind is StopKind.NO_GAIN:
            return f"{self.kind.value} in {self.plateau} inputs"
        return self.kind.value


class MissWhy(StrEnum):
    """What the solver answered about a fork it gave no input for. The words on the line."""

    UNSAT = "unsat"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class Miss:
    """A fork the run asked for and got no input to: where it is, and what the solver said.

    ``raising`` says the fork is an operation's before a raise (``Branch.raising``).
    """

    site: Site
    why: MissWhy
    raising: bool = False


@dataclass(frozen=True)
class Environment:
    """What the run ran in, gathered once per run, in the run layer.

    ``cvc5`` is the version ``cvc5 --version`` reports, or ``None`` when the
    probe failed. A failed probe never stops the run. ``isolated`` says each
    input ran in a process of its own, rather than in pyct's, so a tool
    comparing two runs knows which kind each was.
    """

    python: str
    cvc5: str | None
    platform: str
    isolated: bool


@dataclass(frozen=True)
class SolverCounts:
    """How many times the solver answered each way."""

    sat: int
    unsat: int
    unknown: int
    timeout: int


@dataclass(frozen=True)
class RunResult:
    """One run of one function: its records, the coverage they add up to, and how it ended.

    ``misses`` are the forks the solver gave no input for. A miss is never
    why the run stopped; ``stopped`` carries the loop's own reason.
    ``untried`` counts the forks the run never tried at each site: still open
    when it stopped, or picked and then left by the stop.
    ``deadline`` is the monotonic instant the run's budget ends, None with no budget.
    """

    entry: str
    records: tuple[InputRecord, ...]
    coverage: Coverage
    stopped: Stop
    environment: Environment
    misses: tuple[Miss, ...] = ()
    untried: Mapping[ForkSite, int] = field(default_factory=dict)
    deadline: float | None = None

    @property
    def inputs(self) -> int:
        """How many inputs ran, which is how many lines came before the summary."""
        return len(self.records)

    @property
    def solver(self) -> SolverCounts:
        """What the solver answered, derived so the counts can never disagree with the misses.

        An input the solver gave is its one ``sat``; every other answer gave
        no input and is already a miss.
        """
        whys = [miss.why for miss in self.misses]
        return SolverCounts(
            sat=sum(1 for record in self.records if record.source is Source.SOLVER),
            unsat=whys.count(MissWhy.UNSAT),
            unknown=whys.count(MissWhy.UNKNOWN),
            timeout=whys.count(MissWhy.TIMEOUT),
        )

    @functools.cached_property
    def why_uncovered(self) -> tuple[WhyEntry, ...]:
        """Why each uncovered line was not run, one entry per cause, file by file.

        Worked out the first time it is read, from the module's code and the
        run's inputs, so a caller that never reads it never pays for it. A
        run with a deadline works causes out until at most half a second past
        it, so it still ends within one second of it; the lines left then are
        not worked out.
        """
        # the analysis sees its stop at most one stretch late, so it stops that much early
        grace = ANALYSIS_GRACE - LONGEST_STRETCH
        stop_at = None if self.deadline is None else self.deadline + grace
        run = Run((), {}, stop_at=stop_at)
        # the inputs and their tries are read only when a cause can still be worked out
        if not run.late():
            walked = [
                Walked(record.forks, record.failure is not None, record.covered_lines)
                for record in self.records
            ]
            run = Run(walked, _tries(self), stop_at=stop_at)
        covered = self.coverage.covered
        return tuple(
            entry
            for file, lines in self.coverage.uncovered.items()
            for entry in explain(file, lines, covered.get(file, frozenset()), run)
        )


def _tries(result: RunResult) -> dict[ForkSite, Tries]:
    """What happened at each site each time the run could have flipped a fork there."""
    counts: dict[ForkSite, Counter[str]] = {}
    for where, count in result.untried.items():
        counts.setdefault(where, Counter())["not_tried"] += count
    for miss in result.misses:
        counts.setdefault(ForkSite(miss.site, miss.raising), Counter())[miss.why.value] += 1
    for record in result.records:
        if record.aim is not None and record.mismatch_at is not None:
            aimed = ForkSite(record.aim.site, record.aim.raising)
            counts.setdefault(aimed, Counter())["left_the_plan"] += 1
    fields = [field.name for field in dataclasses.fields(Tries)]
    return {site: Tries(*(counted[name] for name in fields)) for site, counted in counts.items()}
