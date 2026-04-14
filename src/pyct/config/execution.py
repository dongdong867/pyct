"""Execution configuration for the concolic engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    """Configuration for an exploration run.

    Passed to Engine at construction time and frozen for the duration
    of the run. All fields have sensible defaults; override only the
    values you need.

    Attributes:
        timeout_seconds: Hard wall-clock limit on the exploration loop.
        max_iterations: Maximum number of exploration iterations before
            termination, regardless of coverage or time.
        solver: SMT solver binary name (default "cvc5").
        solver_timeout: Per-call solver timeout in seconds.
        plateau_threshold: Iterations without coverage improvement
            before firing the on_coverage_plateau plugin event.
    """

    timeout_seconds: float = 30.0
    max_iterations: int = 50
    solver: str = "cvc5"
    solver_timeout: int = 10
    plateau_threshold: int = 5
