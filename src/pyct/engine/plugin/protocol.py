"""Plugin Protocol — what every engine plugin must provide."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
    """Protocol for extensions to the concolic engine.

    Plugins need only the ``name`` and ``priority`` attributes to be
    recognized as valid Plugin instances. Event handlers are optional:
    the Dispatcher uses getattr to check for handler methods at
    dispatch time, so partial implementations are fully supported.

    A plugin that only cares about seed generation can implement just
    ``on_seed_request`` and ignore every other event.

    Attributes:
        name: Human-readable plugin name, used in logging and errors.
        priority: Ordering within the dispatcher; lower runs first.
            Default convention is 100. Plugins that must run early
            (e.g., LLM seed generation before fuzzing mutation) should
            override to a lower value like 50. Plugins that should run
            late (e.g., fallback strategies) should use a higher value
            like 200.

    Optional event handlers (call conventions):

        Observer events — return value ignored, fire-and-forget:
            def on_exploration_start(self, ctx: EngineContext) -> None
            def on_exploration_end(self, ctx: EngineContext,
                                   result: ExplorationResult) -> None

        Collector events — all plugins run, list results concatenated:
            def on_seed_request(self, ctx: EngineContext) -> list[Seed]
            def on_coverage_plateau(self, ctx: EngineContext) -> list[Seed]

        Resolver events — first non-None return wins, others skipped:
            def on_constraint_unknown(self, ctx: EngineContext,
                                      constraint: Constraint) -> Resolution | None
    """

    name: str
    priority: int
