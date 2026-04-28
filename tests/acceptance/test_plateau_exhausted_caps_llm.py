"""End-to-end AC: plateau early-exit caps the LLM call budget.

Goes through the public ``pyct.run_concolic`` API to verify the
load-bearing property that the unit tests in
``tests/unit/engine/test_plateau_early_exit.py`` only check via direct
calls to ``check_plateau_outcome``: when an LLM-style plugin keeps
returning seeds that fail to improve coverage, the engine must
terminate with ``plateau_exhausted`` after exactly
``max_stale_llm_attempts`` plateau dispatches — no more.

Without this guard, a misbehaving (or rate-limited) LLM oracle would
burn through ``max_iterations`` or ``timeout_seconds`` worth of
plateau dispatches per run, breaking the cost guarantee that the
paper's coverage-gated silencing policy promises.

Spec source: paper §3 (silenced after N stale plateaus); commits
``b352bcd`` (plateau early-exit) and ``ed5c7a7``
(``max_stale_llm_attempts=1`` default). No reference to internal
modules — the test compiles against the published API only.

Test-target shape rationale
---------------------------

The engine exhausts when no constraint solution yields a fresh
merged-with-initial-args input. Constructing a target that *plateaus
twice* through ``run_concolic`` therefore needs:

1. Coverage saturation after the first solver-driven match so that
   subsequent iterations are stale (drives the plateau threshold).
2. An unreachable line (UNSAT-gated ``return 99``) so
   ``is_fully_covered`` stays false and the loop keeps spinning.
3. Branches the LLM-stub plugin can newly expose on each plateau
   dispatch — without growing line coverage. The two-tier
   ``x==100`` / ``x==200`` sub-branches do this: their interior
   ``y==<n>`` arms are only added to the constraint tree when the
   plugin's seed walks through the parent ``x==100=T`` /
   ``x==200=T`` predicates, but every executed line in those paths
   was already covered by the seed iteration.

That shape produces the documented end-to-end sequence: plateau
dispatch → plugin-seed iteration in seed_phase → solver-driven
follow-up iteration → ``check_plateau_outcome`` increments the
failure counter → repeat → terminate ``plateau_exhausted`` once the
counter hits ``max_stale_llm_attempts``.
"""

from __future__ import annotations

from typing import Any

import pyct
from pyct.config.execution import ExecutionConfig


class _CountingStubLLM:
    """LLM oracle stand-in. Records every plateau dispatch and replies
    with seeds that expose new constraint sub-trees but cover no new
    source lines, so the engine fails the silencing check on each
    follow-up iteration."""

    name = "counting_stub_llm"
    priority = 100

    def __init__(self) -> None:
        self.calls = 0
        self._n = 0

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        self.calls += 1
        self._n += 1
        # Each call walks a different ``x`` super-branch (100, 200, 300, …)
        # so the constraint tree gains a fresh sub-tree per dispatch.
        # The ``y`` value never matches any ``y == <n>`` arm so coverage
        # stays flat.
        x = 100 * self._n
        y = 99 + self._n
        return [{"x": x, "y": y}]


def _two_tier_target(x: int, y: int) -> int:
    """Match-arms inline into a single boolean expression so each
    plugin-exposed sub-branch adds NO new executed source line — only
    opens a fresh constraint subtree.

    The ``return 99`` line is gated by an unsatisfiable conjunction so
    ``is_fully_covered`` stays false and the engine keeps iterating
    past coverage saturation.
    """
    matched = (
        (x == 1)
        or (x == 2)
        or (x == 3)
        or ((x == 100) and (y == 10))
        or ((x == 100) and (y == 20))
        or ((x == 200) and (y == 30))
        or ((x == 200) and (y == 40))
    )
    if matched:
        return 1
    if x == 999999 and x == -999999:
        return 99  # unreachable: contradiction keeps coverage < 100%
    return 0


class TestPlateauExhaustedCapsLLMCalls:
    def test_terminates_with_plateau_exhausted_after_budget(self) -> None:
        """AC: the engine stops because the plateau budget exhausted —
        not because iterations or timeout ran out — and the LLM plugin
        was dispatched exactly ``max_stale_llm_attempts`` times."""
        config = ExecutionConfig(
            max_iterations=50,
            timeout_seconds=10.0,
            plateau_threshold=2,
            max_stale_llm_attempts=2,
        )
        plugin = _CountingStubLLM()

        result = pyct.run_concolic(
            _two_tier_target,
            {"x": 0, "y": 0},
            config=config,
            isolated=False,
            plugins=[plugin],
        )

        assert plugin.calls > 0, (
            "the target was supposed to plateau the engine; the LLM plugin "
            "never fired, so this AC tested nothing. "
            f"DEBUG: termination_reason={result.termination_reason}, "
            f"iterations={result.iterations}, paths={result.paths_explored}, "
            f"executed_lines={sorted(result.executed_lines)}"
        )
        assert result.termination_reason == "plateau_exhausted", (
            f"expected plateau_exhausted, got {result.termination_reason!r} "
            f"(plugin called {plugin.calls} times across "
            f"{result.iterations} iterations)"
        )
        assert plugin.calls == config.max_stale_llm_attempts, (
            f"plateau budget was {config.max_stale_llm_attempts}; plugin was "
            f"called {plugin.calls} times — budget cap not enforced"
        )
