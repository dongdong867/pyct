"""Coverage tracking for a concolic target function."""

from __future__ import annotations

from coverage import CoverageData


class CoverageTracker:
    """Accumulates line coverage for a target function across runs.

    Tracks which lines within ``function_lines`` have been executed so far.
    Lines outside the function (e.g., module-level imports picked up by raw
    coverage data) are discarded at update time.

    ``pre_covered`` lets the caller mark some lines as covered at init time
    — used for the ``def`` header, which is part of a function's source
    range but doesn't fire a line event during body execution.
    """

    def __init__(
        self,
        target_file: str,
        function_lines: frozenset[int],
        pre_covered: frozenset[int] = frozenset(),
    ):
        self.target_file = target_file
        self.function_lines = function_lines
        self._covered: set[int] = set(pre_covered & function_lines)

    def update(self, data: CoverageData) -> None:
        """Merge executed lines from ``data`` into the accumulated set."""
        raw_lines = data.lines(self.target_file) or []
        self._covered |= set(raw_lines) & self.function_lines

    @property
    def covered_lines(self) -> frozenset[int]:
        return frozenset(self._covered)

    @property
    def total_lines(self) -> int:
        return len(self.function_lines)

    def is_fully_covered(self) -> bool:
        return self._covered >= self.function_lines
