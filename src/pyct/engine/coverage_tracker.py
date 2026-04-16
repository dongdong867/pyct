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
    range but doesn't fire a line event during body execution. Pre-covered
    lines count toward ``covered_lines`` and ``is_fully_covered()`` but
    are kept separate from tracer-observed lines in ``observed_lines`` so
    downstream consumers can distinguish "really executed" from
    "synthetically counted as covered".
    """

    def __init__(
        self,
        target_file: str,
        function_lines: frozenset[int],
        pre_covered: frozenset[int] = frozenset(),
    ):
        self.target_file = target_file
        self.function_lines = function_lines
        self._pre_covered: frozenset[int] = frozenset(pre_covered & function_lines)
        self._observed: set[int] = set()

    def update(self, data: CoverageData) -> None:
        """Merge tracer-observed lines from ``data`` into the observed set."""
        raw_lines = data.lines(self.target_file) or []
        self._observed |= set(raw_lines) & self.function_lines

    @property
    def covered_lines(self) -> frozenset[int]:
        """Lines considered covered — tracer-observed ∪ pre-covered."""
        return frozenset(self._observed | self._pre_covered)

    @property
    def observed_lines(self) -> frozenset[int]:
        """Lines the tracer actually saw fire, excluding pre-covered."""
        return frozenset(self._observed)

    @property
    def total_lines(self) -> int:
        return len(self.function_lines)

    def is_fully_covered(self) -> bool:
        return (self._observed | self._pre_covered) >= self.function_lines
