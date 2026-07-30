"""Unit tests for optional static-analysis context in seed prompts.

The seed prompt carries three independently switchable context blocks:
callee sources, the CFG, and aggregated boundary values. Each maps to a
flag on :class:`PromptContextOptions` so an experiment can measure the
marginal effect of one block without the others.

With every flag off the prompt must be byte-identical to the source-only
prompt, so the default path stays exactly what the engine shipped.
"""

from __future__ import annotations

import inspect

import pytest

from pyct.config.execution import ExecutionConfig
from pyct.engine.plugin.context import EngineContext
from pyct.plugins.llm.prompt import PromptContextOptions, build_seed_prompt

MAX_ATTEMPTS = 3

VALID_MODES = frozenset({"fast", "safe"})


def _threshold_check(value: int) -> str:
    """Callee whose branch predicate is invisible from the caller."""
    if value > MAX_ATTEMPTS:
        return "over"
    return "under"


def _mode_check(mode: str) -> str:
    if mode in VALID_MODES:
        return "known"
    return "unknown"


def target(value: int, mode: str) -> str:
    """Entry point that delegates both predicates to helpers."""
    if value < 0:
        return "negative"
    first = _threshold_check(value)
    return first + _mode_check(mode)


def _leaf(flag: bool) -> str:
    """Target with no project-internal callees."""
    if flag:
        return "yes"
    return "no"


def _context_for(func) -> EngineContext:
    return EngineContext(
        iteration=0,
        constraint_pool=(),
        covered_lines=frozenset(),
        total_lines=0,
        inputs_tried=(),
        target_function=func,
        target_signature=inspect.signature(func),
        config=ExecutionConfig(),
        elapsed_seconds=0.0,
    )


@pytest.fixture
def ctx() -> EngineContext:
    return _context_for(target)


class TestCalleeContext:
    """``include_callees`` adds callee bodies and their branch conditions."""

    def test_callee_body_included_when_enabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert "def _threshold_check(" in prompt
        assert "def _mode_check(" in prompt

    def test_callee_branch_predicate_included_when_enabled(self, ctx: EngineContext) -> None:
        """The predicate the caller cannot show is what makes this worth sending."""
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert "value > MAX_ATTEMPTS" in prompt

    def test_callee_body_absent_when_disabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=False))
        assert "def _threshold_check(" not in prompt

    def test_target_without_callees_emits_no_callee_section(self) -> None:
        prompt = build_seed_prompt(_context_for(_leaf), PromptContextOptions(include_callees=True))
        assert "Called Function:" not in prompt


class TestCfgContext:
    """``include_cfg`` adds the control-flow graph block."""

    def test_cfg_included_when_enabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_cfg=True))
        assert "Control Flow Graph" in prompt

    def test_cfg_absent_when_disabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_cfg=False))
        assert "Control Flow Graph" not in prompt


class TestBoundaryValueContext:
    """``include_boundary_values`` adds the aggregated literal block."""

    def test_boundary_values_included_when_enabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(
            ctx, PromptContextOptions(include_callees=True, include_boundary_values=True)
        )
        assert "Boundary Values" in prompt

    def test_boundary_values_absent_when_disabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(
            ctx,
            PromptContextOptions(include_callees=True, include_boundary_values=False),
        )
        assert "Boundary Values" not in prompt


class TestDefaultsPreserveShippedPrompt:
    """All flags off must reproduce the source-only prompt exactly."""

    def test_all_flags_off_matches_no_options(self, ctx: EngineContext) -> None:
        assert build_seed_prompt(ctx, PromptContextOptions()) == build_seed_prompt(ctx)

    def test_no_options_carries_no_analysis_sections(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx)
        for marker in ("Control Flow Graph", "Called Function:", "Boundary Values"):
            assert marker not in prompt


class TestAnalysisFailureDegrades:
    """A target whose module cannot be resolved must not break seeding."""

    def test_unresolvable_module_still_builds_prompt(self) -> None:
        namespace: dict[str, object] = {}
        exec("def synthetic(x: int) -> int:\n    return x + 1\n", namespace)
        synthetic = namespace["synthetic"]

        prompt = build_seed_prompt(
            _context_for(synthetic),
            PromptContextOptions(
                include_callees=True, include_cfg=True, include_boundary_values=True
            ),
        )
        assert "# Task: Generate Test Inputs" in prompt
