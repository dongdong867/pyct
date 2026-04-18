"""Post-loop discovery phase.

After the main exploration loop exits, if coverage is still incomplete
the engine runs up to ``post_loop_rounds`` rounds of LLM-driven gap
closing. Each round dispatches the ``on_post_loop_discovery`` collector
event, executes the returned candidate inputs, then runs a bounded
solver mini-loop (``post_loop_mini_iterations``) to exploit any new
constraints before the next round. The silencing counter from Stage 2
(``max_stale_llm_attempts``) gates the phase: after that many
consecutive non-improving rounds the phase exits early.

Matches the paper's Algorithm 3 and legacy's ``_attempt_post_loop_coverage``.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine


class _PostLoopPlugin:
    """Returns scripted seeds for the first K ``on_post_loop_discovery`` calls.

    After the script is exhausted, returns ``[]`` so a run never depends on
    implicit silencing to stop.
    """

    name = "post_loop"
    priority = 100

    def __init__(self, rounds: list[list[dict[str, Any]]]):
        self._rounds = rounds
        self.calls = 0

    def on_post_loop_discovery(self, ctx: Any) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls > len(self._rounds):
            return []
        return list(self._rounds[self.calls - 1])


def _regex_gate(x: str) -> int:
    """Branch the SMT solver cannot reason about on its own — main loop
    will end with the ``x == 'hello'`` path uncovered, giving post-loop
    discovery something to close."""
    import re

    if re.match(r"^hello$", x):
        return 1
    return 0


def _two_gates(x: str) -> int:
    """Two independent regex gates; each closed path costs one LLM seed."""
    import re

    if re.match(r"^foo$", x):
        return 1
    if re.match(r"^bar$", x):
        return 2
    return 0


class TestPostLoopDispatch:
    def test_fires_after_main_loop_exits_incomplete(self) -> None:
        """A partial-coverage main loop triggers at least one post-loop round."""
        config = ExecutionConfig(
            max_iterations=5, timeout_seconds=5.0, post_loop_rounds=3
        )
        engine = Engine(config)
        plugin = _PostLoopPlugin(rounds=[[{"x": "hello"}]])
        engine.register(plugin)

        engine.explore(_regex_gate, {"x": ""})

        assert plugin.calls >= 1, "on_post_loop_discovery should fire after an incomplete main loop"

    def test_skipped_on_full_coverage(self) -> None:
        """If the main loop reaches 100%, post-loop discovery is unnecessary."""
        config = ExecutionConfig(max_iterations=20, timeout_seconds=5.0)
        engine = Engine(config)
        plugin = _PostLoopPlugin(rounds=[[{"x": "hello"}]])
        engine.register(plugin)

        def _solvable(x: int) -> int:
            if x > 0:
                return 1
            return 0

        engine.explore(_solvable, {"x": 0})

        assert plugin.calls == 0, "post-loop must not fire when main loop hits full coverage"


class TestPostLoopSilencing:
    def test_silences_after_two_non_improving_rounds(self) -> None:
        """Two consecutive empty-improvement rounds → phase exits early."""
        config = ExecutionConfig(
            max_iterations=5,
            timeout_seconds=5.0,
            post_loop_rounds=5,
            max_stale_llm_attempts=2,
        )
        engine = Engine(config)
        # Every round returns the same useless seed → zero improvement.
        useless = {"x": ""}
        plugin = _PostLoopPlugin(rounds=[[useless]] * 5)
        engine.register(plugin)

        engine.explore(_regex_gate, {"x": ""})

        assert plugin.calls == 2, (
            f"expected silencing after 2 non-improving rounds, "
            f"got {plugin.calls} plugin calls"
        )

    def test_improvement_resets_silencing_counter(self) -> None:
        """An improving round followed by non-improving rounds should still
        run ``max_stale_llm_attempts`` non-improving rounds before silencing."""
        config = ExecutionConfig(
            max_iterations=5,
            timeout_seconds=5.0,
            post_loop_rounds=5,
            max_stale_llm_attempts=2,
        )
        engine = Engine(config)
        plugin = _PostLoopPlugin(
            rounds=[
                [{"x": "foo"}],  # improves — covers first gate
                [{"x": ""}],     # no improvement
                [{"x": ""}],     # no improvement → silenced on this round
                [{"x": "bar"}],  # never reached
            ]
        )
        engine.register(plugin)

        engine.explore(_two_gates, {"x": ""})

        assert plugin.calls == 3, (
            f"improvement should reset the counter; expected 1 improving + "
            f"2 non-improving rounds before silencing, got {plugin.calls}"
        )


class TestPostLoopRoundsCap:
    def test_respects_post_loop_rounds_cap(self) -> None:
        """Even with improvement every round, the phase stops at
        ``post_loop_rounds``."""
        config = ExecutionConfig(
            max_iterations=5,
            timeout_seconds=5.0,
            post_loop_rounds=1,
            max_stale_llm_attempts=5,
        )
        engine = Engine(config)
        plugin = _PostLoopPlugin(
            rounds=[
                [{"x": "foo"}],
                [{"x": "bar"}],
            ]
        )
        engine.register(plugin)

        engine.explore(_two_gates, {"x": ""})

        assert plugin.calls == 1, "post_loop_rounds=1 must cap the phase at one call"
