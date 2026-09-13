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

    @property
    def reached(self) -> bool:
        """Whether the run followed the whole plan it was solved for."""
        return self.mismatch_at is None


class StopKind(StrEnum):
    """Why a run ended. The values are the words on the ``stopped`` line."""

    NO_FORK = "no fork to flip"
    BUDGET = "budget spent"
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
class RunResult:
    """One run of one function: its records, the coverage they add up to, and how it ended.

    ``misses`` are the forks the solver gave no input for. A miss is never
    why the run stopped; ``stopped`` carries the loop's own reason.
    """

    entry: str
    records: tuple[InputRecord, ...]
    coverage: Coverage
    stopped: Stop
    misses: tuple[Miss, ...] = ()
