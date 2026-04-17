"""Coverage tracking for a concolic target, scoped by CoverageScope."""

from __future__ import annotations

from coverage import CoverageData

from pyct.engine.coverage_scope import CoverageScope


class CoverageTracker:
    """Accumulates line coverage against a CoverageScope.

    The scope specifies which files to track and which lines within each
    file are executable. Lines outside the scope's executable sets are
    discarded at update time.

    Exposes two complementary views:

    - **Narrow** (``target_file``, ``function_lines``, ``covered_lines``,
      ``observed_lines``): reports only the scope's primary target file.
      Feeds plugin snapshots and ``ExplorationResult.executed_lines`` so
      LLM prompts stay focused on the target function's own source.
    - **Wide** (``total_lines``, ``covered_count``, ``observed_count``,
      ``coverage_percent``, ``is_fully_covered``): spans every file in
      the scope. Drives the engine's termination and plateau decisions
      — ``is_fully_covered`` only returns True when every scope file's
      executable lines are observed or pre-covered.

    Pre-covered lines come from the scope and count toward ``covered*``
    views and ``is_fully_covered`` but not toward ``observed*`` — so
    downstream consumers can distinguish "really executed" from
    "synthetically counted as covered" (the ``def`` header is the
    classic case).
    """

    def __init__(self, scope: CoverageScope):
        self.scope = scope
        self._observed: dict[str, set[int]] = {f: set() for f in scope.files}

    def update(self, data: CoverageData) -> None:
        """Merge tracer-observed lines from ``data`` for every scope file."""
        for path in self.scope.files:
            raw_lines = data.lines(path) or []
            allowed = self.scope.executable_lines.get(path, frozenset())
            self._observed[path] |= set(raw_lines) & allowed

    # ── Narrow views (target file only) ───────────────────────────────

    @property
    def target_file(self) -> str:
        return self.scope.target_file

    @property
    def function_lines(self) -> frozenset[int]:
        """Executable lines within the primary target file."""
        return self.scope.executable_lines.get(self.target_file, frozenset())

    @property
    def observed_lines(self) -> frozenset[int]:
        """Lines the tracer fired on within the primary target file."""
        return frozenset(self._observed.get(self.target_file, set()))

    @property
    def covered_lines(self) -> frozenset[int]:
        """Observed ∪ pre-covered lines within the primary target file."""
        observed = self._observed.get(self.target_file, set())
        pre = self.scope.pre_covered.get(self.target_file, frozenset())
        return frozenset(observed | (pre & self.function_lines))

    # ── Wide views (every scope file) ─────────────────────────────────

    @property
    def total_lines(self) -> int:
        """Sum of executable lines across all scope files."""
        return self.scope.total_lines

    @property
    def observed_count(self) -> int:
        """Count of tracer-observed lines across all scope files."""
        return sum(len(s) for s in self._observed.values())

    @property
    def covered_count(self) -> int:
        """Count of observed ∪ pre-covered lines across all scope files."""
        total = 0
        for path in self.scope.files:
            allowed = self.scope.executable_lines.get(path, frozenset())
            pre = self.scope.pre_covered.get(path, frozenset())
            total += len(self._observed[path] | (pre & allowed))
        return total

    @property
    def coverage_percent(self) -> float:
        """Wide coverage ratio as a 0-100 percentage."""
        total = self.total_lines
        if total == 0:
            return 0.0
        return 100.0 * self.covered_count / total

    def is_fully_covered(self) -> bool:
        """True when every scope file's executable lines are covered."""
        for path in self.scope.files:
            needed = self.scope.executable_lines.get(path, frozenset())
            observed = self._observed[path]
            pre = self.scope.pre_covered.get(path, frozenset())
            if not (observed | pre) >= needed:
                return False
        return True
