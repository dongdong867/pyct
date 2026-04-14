"""Engine — the concolic exploration orchestrator (M2-B.1 stub)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.plugin.protocol import Plugin
from pyct.engine.result import ExplorationResult


class Engine:
    """Orchestrates concolic exploration of a target function.

    Plugins are registered via ``engine.register(plugin_instance)``
    and receive events during the exploration loop. See
    ``pyct.engine.plugin`` documentation for event semantics.

    Example:
        from pyct import Engine, ExecutionConfig
        engine = Engine(ExecutionConfig(max_iterations=50))
        engine.register(MyPlugin())
        result = engine.explore(target_function, {"x": 0})
    """

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance with the engine.

        Plugins are ordered by their ``priority`` attribute (lower
        runs earlier), with registration order as a tiebreaker.

        TODO(v2): Add a config-driven registration path
        (``Engine.from_config(cfg)``) that looks up plugin names in a
        registry and instantiates them with parameters from the config
        file. Explicit instantiation is preferred for v1 because
        plugin constructors take parameters (LLM api_key, fuzzing
        mutation_rate) that are simpler to pass as Python kwargs than
        as registry lookups.
        """
        self.plugins.append(plugin)

    def explore(
        self,
        target: Callable,
        initial_args: dict[str, Any],
    ) -> ExplorationResult:
        """Run concolic exploration on ``target`` starting from ``initial_args``.

        Returns an ExplorationResult describing the outcome. Termination
        is engine-decided based on full coverage, timeout, max
        iterations, or constraint pool exhaustion — no plugin
        cancellation in v1.

        NOTE: Not yet implemented. This is the M2-B.1 stub. The real
        implementation lands in M2-B.2 with the concolic execution
        loop, path constraint collection, and solver-driven input
        generation.
        """
        raise NotImplementedError(
            "Engine.explore() not yet implemented — pending M2-B.2"
        )
