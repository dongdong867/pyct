"""One input's record, and the result of one run."""

from collections.abc import Mapping
from dataclasses import dataclass

from pyct.results.coverage import Coverage


@dataclass(frozen=True)
class InputRecord:
    """What one input did: the arguments it ran with and the lines it reached."""

    args: Mapping[str, object]
    covered_lines: frozenset[int]


@dataclass(frozen=True)
class RunResult:
    """One run of one function: its records and the coverage they add up to."""

    entry: str
    records: tuple[InputRecord, ...]
    coverage: Coverage
