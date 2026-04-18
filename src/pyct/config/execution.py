"""Execution configuration for the concolic engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyct.engine.coverage_scope import CoverageScope


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
        max_stale_llm_attempts: Number of consecutive non-improving
            LLM dispatches tolerated before exploration exits the
            phase. Applies to both the in-loop plateau trigger (which
            terminates the main loop with ``plateau_exhausted``) and
            the post-loop discovery push. Default of 1 matches the
            paper's coverage-gated silencing policy: "silenced as
            soon as it fails to improve coverage". Set to 2 for
            legacy post-loop behavior.
        post_loop_rounds: Upper bound on rounds of post-loop discovery
            that run after the main loop exits with partial coverage.
            Each round dispatches ``on_post_loop_discovery`` and may
            close a portion of the remaining gap. Zero disables the
            phase entirely.
        post_loop_mini_iterations: Solver iteration cap used within
            each post-loop round to exploit fresh constraints collected
            from the plugin's candidate inputs.
        seed_soft_timeout: Per-seed wall-clock cap for the seed-replay
            phase. Seed iterations are exempt from ``max_iterations``
            and ``timeout_seconds``; this bound is what protects the
            engine from a hung or pathological seed. Mirrors the
            ``_coverage_by_rerun`` / ``run_llm_only`` protection in
            ``tools/benchmark/runners.py``.
        scope: Optional CoverageScope specifying which source files the
            engine tracks for coverage and termination. When None
            (default), the engine constructs a narrow single-file scope
            from the target function — identical to classical concolic
            testing behavior. Set to a multi-file scope when the caller
            wants the engine to keep exploring past the target function
            until deeper library code is also covered.
    """

    timeout_seconds: float = 30.0
    max_iterations: int = 50
    solver: str = "cvc5"
    solver_timeout: int = 10
    plateau_threshold: int = 5
    max_stale_llm_attempts: int = 1
    post_loop_rounds: int = 3
    post_loop_mini_iterations: int = 20
    seed_soft_timeout: float = 10.0
    scope: CoverageScope | None = None
