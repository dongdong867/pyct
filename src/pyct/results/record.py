"""One input's record, and the result of one run."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure


class Source(StrEnum):
    """Where an input came from. The values are the words on the line."""

    SEED = "seed"
    SOLVER = "solver"


@dataclass(frozen=True)
class Aim:
    """The fork an input was solved for: where it is, and where on the path."""

    site: Site
    position: int


@dataclass(frozen=True)
class DowngradeCount:
    """A run of consecutive calls of one dunder that dropped the condition."""

    name: str
    count: int


@dataclass(frozen=True)
class InputRecord:
    """What one input did: its arguments, the forks it took, the lines it reached.

    ``failure`` is how it ended when it did not return. ``downgrades`` names
    each call that dropped the condition, in order, a run of one dunder
    counted as a single entry.

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
    """Why a run ended. The values are the words on the ``stopped`` line."""

    NO_FORK = "no fork to flip"
    BUDGET = "budget spent"
    # transitional: one flip is the whole loop today, and this leaves with the
    # loop ticket loop-until-no-fork-is-left
    ONE_ATTEMPT = "after one attempt"
    SOLVER_FAILED = "solver failed"


@dataclass(frozen=True)
class Stop:
    """How the run ended, and, when the solver failed, what it said."""

    kind: StopKind
    detail: str | None = None


class MissWhy(StrEnum):
    """What the solver answered about a fork it gave no input for. The words on the line."""

    UNSAT = "unsat"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class Miss:
    """A fork the run asked for and got no input to: where it is, and what the solver said."""

    site: Site
    why: MissWhy


@dataclass(frozen=True)
class Environment:
    """What the run ran in, gathered once per run, in the run layer.

    ``cvc5`` is the version ``cvc5 --version`` reports, or ``None`` when the
    probe failed. A failed probe never stops the run.
    """

    python: str
    cvc5: str | None
    platform: str


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
    """

    entry: str
    records: tuple[InputRecord, ...]
    coverage: Coverage
    stopped: Stop
    environment: Environment
    misses: tuple[Miss, ...] = ()

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
