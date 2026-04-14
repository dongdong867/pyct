"""EngineContext — read-only snapshot of engine state passed to plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import Signature
from typing import Any

from pyct.config.execution import ExecutionConfig


@dataclass(frozen=True)
class EngineContext:
    """Immutable snapshot of engine state when a plugin event fires.

    Plugins receive this object as their first argument when any event
    handler is called. It exposes enough state for plugins to make
    decisions (iteration number, coverage so far, inputs already tried,
    target signature) without giving them mutation access to the
    engine. Plugins communicate back to the engine exclusively through
    their return values.

    Attributes:
        iteration: Current iteration count.
        constraint_pool: Snapshot of unexplored path constraints.
        covered_lines: Source line numbers hit so far.
        total_lines: Total executable lines in the target.
        inputs_tried: Snapshot of inputs already executed.
        target_function: The function being tested.
        target_signature: Inspected signature of target_function.
        config: The engine's frozen ExecutionConfig.
        elapsed_seconds: Wall-clock seconds since exploration began.
    """

    iteration: int
    constraint_pool: tuple[Any, ...]
    covered_lines: frozenset[int]
    total_lines: int
    inputs_tried: tuple[dict[str, Any], ...]
    target_function: Callable
    target_signature: Signature
    config: ExecutionConfig
    elapsed_seconds: float

    @property
    def coverage_percent(self) -> float:
        """Return coverage as a 0-100 percentage."""
        if self.total_lines == 0:
            return 0.0
        return 100.0 * len(self.covered_lines) / self.total_lines
