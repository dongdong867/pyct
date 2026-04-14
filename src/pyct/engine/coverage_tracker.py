"""Coverage tracking — M2-B.2a stub (behavior pending in GREEN commit)."""

from __future__ import annotations

from coverage import CoverageData


class CoverageTracker:
    """Accumulates line coverage for a target function across runs.

    M2-B.2a stub — construction and trivial properties are real so
    tests can exercise the type contract, but update() and
    is_fully_covered() raise NotImplementedError until the GREEN
    commit wires up the algorithm.
    """

    def __init__(self, target_file: str, function_lines: frozenset[int]):
        self.target_file = target_file
        self.function_lines = function_lines
        self._covered: set[int] = set()

    def update(self, data: CoverageData) -> None:
        raise NotImplementedError(
            "CoverageTracker.update not yet implemented — pending M2-B.2a GREEN"
        )

    @property
    def covered_lines(self) -> frozenset[int]:
        return frozenset(self._covered)

    @property
    def total_lines(self) -> int:
        return len(self.function_lines)

    def is_fully_covered(self) -> bool:
        raise NotImplementedError(
            "CoverageTracker.is_fully_covered not yet implemented — pending M2-B.2a GREEN"
        )
