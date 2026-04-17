"""Exploration result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExplorationResult:
    """Internal result produced by Engine.explore().

    Summarizes an exploration run. The public-facing counterpart is
    RunConcolicResult, which exposes the same data via
    ``inputs_generated`` + ``from_exploration()`` for API stability.

    Coverage is reported along two dimensions:
      - ``coverage_percent`` / ``executed_lines``: narrow view (target
        file's own lines only), preserved for plugin prompts and
        backward compat with callers that expected single-file data.
      - ``scope_coverage_percent`` / ``scope_executed_lines`` /
        ``scope_total_lines``: wide view across every file in the
        engine's CoverageScope. Populated from the engine's in-loop
        line tracer and comparable to the benchmark's post-hoc rerun
        measurement — the two numbers agreeing strengthens validity.

    Attributes:
        success: True if exploration completed without error.
        coverage_percent: Narrow (target-file) line coverage as 0-100.
        executed_lines: Lines hit in the target's own file.
        paths_explored: Number of distinct input combinations tried.
        iterations: Number of exploration loop iterations.
        termination_reason: One of "full_coverage", "max_iterations",
            "timeout", "exhausted", or "error".
        elapsed_seconds: Wall-clock duration of the exploration.
        error: Human-readable error message if success=False, else None.
        inputs_generated: Inputs the engine executed during exploration.
        scope_coverage_percent: Wide (scope-spanning) coverage percent.
        scope_executed_lines: ``{(file, line)}`` pairs across the scope.
        scope_total_lines: Sum of executable lines across all scope files.
    """

    success: bool
    coverage_percent: float
    executed_lines: frozenset[int]
    paths_explored: int
    iterations: int
    termination_reason: str
    elapsed_seconds: float
    error: str | None = None
    inputs_generated: tuple[dict[str, Any], ...] = ()
    scope_coverage_percent: float = 0.0
    scope_executed_lines: frozenset[tuple[str, int]] = frozenset()
    scope_total_lines: int = 0


@dataclass(frozen=True)
class RunConcolicResult:
    """Public result returned by pyct.run_concolic().

    Adds inputs_generated compared to ExplorationResult so callers
    can see what test inputs the engine produced. Internal fields
    (engine state, constraint pool) are NOT exposed.

    Use RunConcolicResult.from_exploration(exploration, inputs) to
    construct one from an internal ExplorationResult.
    """

    success: bool
    coverage_percent: float
    executed_lines: frozenset[int]
    paths_explored: int
    inputs_generated: tuple[dict[str, Any], ...]
    iterations: int
    termination_reason: str
    error: str | None = None
    token_stats: dict[str, int] | None = None
    scope_coverage_percent: float = 0.0
    scope_executed_lines: frozenset[tuple[str, int]] = frozenset()
    scope_total_lines: int = 0

    @classmethod
    def from_exploration(
        cls,
        result: ExplorationResult,
        inputs: list[dict[str, Any]],
        token_stats: dict[str, int] | None = None,
    ) -> RunConcolicResult:
        """Construct a public result from an internal ExplorationResult.

        Args:
            result: Internal exploration result from Engine.explore().
            inputs: Inputs that were executed during exploration.

        Returns:
            Public result with inputs_generated populated.
        """
        return cls(
            success=result.success,
            coverage_percent=result.coverage_percent,
            executed_lines=result.executed_lines,
            paths_explored=result.paths_explored,
            inputs_generated=tuple(inputs),
            iterations=result.iterations,
            termination_reason=result.termination_reason,
            error=result.error,
            token_stats=token_stats,
            scope_coverage_percent=result.scope_coverage_percent,
            scope_executed_lines=result.scope_executed_lines,
            scope_total_lines=result.scope_total_lines,
        )
