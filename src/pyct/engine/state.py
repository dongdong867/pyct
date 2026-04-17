"""Internal exploration state — mutable, owned by the engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExplorationState:
    """Mutable state for an in-progress exploration run.

    This is engine-internal. Plugins receive a read-only snapshot via
    EngineContext, not this object directly. The engine updates this
    state in place as exploration progresses.

    Attributes:
        iteration: Current iteration count, starting at zero.
        constraint_pool: Path constraints awaiting exploration.
        covered_lines: Set of source line numbers hit so far, including
            synthetic pre-covered headers (used for plateau detection
            and coverage_percent reporting during exploration).
        observed_lines: Subset of covered_lines that the tracer actually
            saw fire — excludes pre-covered. This is what gets reported
            to callers as ``executed_lines`` so downstream def-header
            backfill heuristics work correctly.
        total_lines: Total executable lines in the target function.
        inputs_tried: History of inputs that have been executed.
        start_time: Wall-clock start time (from time.monotonic()).
        last_coverage_change_iteration: Iteration number when coverage
            last increased. Used to detect plateaus.
        terminated: True once the engine has stopped exploring.
        termination_reason: Human-readable reason for termination, or
            None if still running.
        seed_phase: True while the engine is still replaying pre-supplied
            or plateau-requested seeds. While True, ``max_iterations``
            and ``timeout_seconds`` do not apply — only the per-seed
            soft timeout bounds each iteration. Flipped to False in
            ``_next_input`` when the input queue first drains, and
            re-enabled by ``_handle_plateau`` when new plugin seeds are
            appended to the queue.
    """

    iteration: int = 0
    constraint_pool: list[Any] = field(default_factory=list)
    covered_lines: set[int] = field(default_factory=set)
    observed_lines: set[int] = field(default_factory=set)
    total_lines: int = 0
    inputs_tried: list[dict[str, Any]] = field(default_factory=list)
    start_time: float = 0.0
    last_coverage_change_iteration: int = 0
    terminated: bool = False
    termination_reason: str | None = None
    seed_phase: bool = True

    def coverage_percent(self) -> float:
        """Return coverage as a 0-100 percentage."""
        if self.total_lines == 0:
            return 0.0
        return 100.0 * len(self.covered_lines) / self.total_lines

    def paths_explored(self) -> int:
        """Return the number of distinct inputs that have been tried."""
        return len(self.inputs_tried)

    def elapsed_seconds(self) -> float:
        """Return wall-clock seconds since start_time was set."""
        return time.monotonic() - self.start_time
