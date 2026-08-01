"""Unit tests for callee context in seed prompts.

The seed prompt carries one optional block: the source of every
function the target reaches, inlined into the target's own code fence.
Callees read as source because that is the form the model already
consumes — a derived restatement of the same predicates carries no fact
the source does not.

With the flag off the prompt must be byte-identical to the source-only
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


def _target_code_block(prompt: str) -> str:
    """Return the body of the first ``python`` fence in *prompt*."""
    _, _, after_open = prompt.partition("```python\n")
    body, _, _ = after_open.partition("\n```")
    return body


@pytest.fixture
def ctx() -> EngineContext:
    return _context_for(target)


class TestCalleeSourceInlined:
    """``include_callees`` inlines reachable sources into the target fence."""

    def test_callee_source_included_when_enabled(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert "def _threshold_check(" in prompt
        assert "def _mode_check(" in prompt

    def test_callee_branch_predicate_included_when_enabled(self, ctx: EngineContext) -> None:
        """The predicate the caller cannot show is what makes this worth sending."""
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert "value > MAX_ATTEMPTS" in prompt

    def test_callees_share_the_target_code_fence(self, ctx: EngineContext) -> None:
        """One fence, so the block reads as a module rather than an appendix."""
        block = _target_code_block(
            build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        )
        assert "def target(" in block
        assert "def _threshold_check(" in block
        assert "def _mode_check(" in block

    def test_each_callee_is_attributed_to_its_caller(self, ctx: EngineContext) -> None:
        block = _target_code_block(
            build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        )
        assert block.count("# called by target") == 2

    def test_callees_follow_call_order(self, ctx: EngineContext) -> None:
        block = _target_code_block(
            build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        )
        assert block.index("def _threshold_check(") < block.index("def _mode_check(")

    def test_request_names_the_called_functions(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert "in the functions it calls" in prompt


class TestDerivedBlocksRemoved:
    """No block restates predicates the inlined source already carries."""

    @pytest.mark.parametrize(
        "marker",
        [
            "Control Flow Graph",
            "Call Graph Analysis",
            "Called Function:",
            "Aggregated Constraints",
            "Branch conditions:",
            "Boundary Values",
        ],
    )
    def test_marker_absent_with_callees_enabled(self, ctx: EngineContext, marker: str) -> None:
        prompt = build_seed_prompt(ctx, PromptContextOptions(include_callees=True))
        assert marker not in prompt

    def test_options_expose_only_the_callee_switch(self) -> None:
        """Guards against a removed block returning behind a new default-on flag."""
        fields = set(PromptContextOptions.__dataclass_fields__)
        assert fields == {"include_callees", "max_depth"}


class TestDefaultsPreserveShippedPrompt:
    """Flag off must reproduce the source-only prompt exactly."""

    def test_flag_off_matches_no_options(self, ctx: EngineContext) -> None:
        assert build_seed_prompt(ctx, PromptContextOptions()) == build_seed_prompt(ctx)

    def test_no_options_carries_no_callee_source(self, ctx: EngineContext) -> None:
        prompt = build_seed_prompt(ctx)
        assert "def _threshold_check(" not in prompt
        assert "# called by" not in prompt


class TestTargetsWithoutCallees:
    """A leaf target gains nothing and must not gain an empty scaffold."""

    def test_leaf_target_emits_no_attribution_marker(self) -> None:
        prompt = build_seed_prompt(_context_for(_leaf), PromptContextOptions(include_callees=True))
        assert "# called by" not in prompt

    def test_leaf_target_still_carries_its_own_source(self) -> None:
        prompt = build_seed_prompt(_context_for(_leaf), PromptContextOptions(include_callees=True))
        assert "def _leaf(" in prompt


class TestAnalysisFailureDegrades:
    """A target whose module cannot be resolved must not break seeding."""

    def test_unresolvable_module_still_builds_prompt(self) -> None:
        namespace: dict[str, object] = {}
        exec("def synthetic(x: int) -> int:\n    return x + 1\n", namespace)
        synthetic = namespace["synthetic"]

        prompt = build_seed_prompt(
            _context_for(synthetic),
            PromptContextOptions(include_callees=True),
        )
        assert "# Task: Generate Test Inputs" in prompt
