"""One input's record, and the result of one run."""

from collections.abc import Mapping
from dataclasses import dataclass

from pyct.core.branch import Branch
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure


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
    """

    args: Mapping[str, object]
    forks: tuple[Branch, ...]
    covered_lines: frozenset[int]
    failure: Failure | None = None
    downgrades: tuple[DowngradeCount, ...] = ()


@dataclass(frozen=True)
class RunResult:
    """One run of one function: its records and the coverage they add up to."""

    entry: str
    records: tuple[InputRecord, ...]
    coverage: Coverage
