"""Unit tests for pyct.plugins.llm.prompt — prompt builders.

Three scenarios:
- ``build_seed_prompt(ctx)`` — initial seed generation from source + signature
- ``build_plateau_prompt(ctx)`` — plateau recovery with tried inputs + missing lines
- ``build_unknown_prompt(ctx, constraint)`` — solver failure with the failing constraint

Each builder returns a string. Tests assert critical sections are
present so prompt changes surface as failures rather than silent
behavior drift.
"""

from __future__ import annotations


def _simple_target(value: int) -> str:
    if value > 10:
        return "big"
    return "small"


def _build_context(inputs_tried=(), covered_lines=frozenset()):
    import inspect

    from pyct.config.execution import ExecutionConfig
    from pyct.engine.plugin.context import EngineContext

    return EngineContext(
        iteration=len(inputs_tried),
        constraint_pool=(),
        covered_lines=covered_lines,
        total_lines=4,
        inputs_tried=tuple(inputs_tried),
        target_function=_simple_target,
        target_signature=inspect.signature(_simple_target),
        config=ExecutionConfig(),
        elapsed_seconds=0.0,
    )


class TestSeedPrompt:
    def test_seed_prompt_includes_target_source(self):
        from pyct.plugins.llm.prompt import build_seed_prompt

        prompt = build_seed_prompt(_build_context())
        assert "def _simple_target" in prompt
        assert 'return "big"' in prompt or "'big'" in prompt

    def test_seed_prompt_includes_signature(self):
        from pyct.plugins.llm.prompt import build_seed_prompt

        prompt = build_seed_prompt(_build_context())
        assert "value" in prompt  # parameter name

    def test_seed_prompt_requests_list_format(self):
        from pyct.plugins.llm.prompt import build_seed_prompt

        prompt = build_seed_prompt(_build_context())
        # Should explicitly ask for a list of dicts so the parser has
        # something to grab onto
        assert "list" in prompt.lower()
        assert "dict" in prompt.lower()


class TestSeedPromptParameterFiltering:
    """``build_seed_prompt`` must exclude parameters whose defaults aren't
    Python literals (e.g., ``Callable`` defaults). Otherwise the LLM fills
    them in with ``None``, which poisons the call at runtime — see
    ``validators.url``'s ``validate_scheme`` parameter.
    """

    @staticmethod
    def _target_with_callable_default(value: str, /, *, fn=len) -> int:
        return fn(value)

    def _context_for(self, target):
        import inspect

        from pyct.config.execution import ExecutionConfig
        from pyct.engine.plugin.context import EngineContext

        return EngineContext(
            iteration=0,
            constraint_pool=(),
            covered_lines=frozenset(),
            total_lines=2,
            inputs_tried=(),
            target_function=target,
            target_signature=inspect.signature(target),
            config=ExecutionConfig(),
            elapsed_seconds=0.0,
        )

    def test_seed_prompt_parameter_list_omits_callable_default_param(self):
        from pyct.plugins.llm.prompt import build_seed_prompt

        prompt = build_seed_prompt(self._context_for(self._target_with_callable_default))

        # The "these exact parameter names: [...]" line must list only
        # literalizable params — ``fn`` (callable default) must not appear
        # in that list.
        line = next(ln for ln in prompt.splitlines() if "exact parameter names" in ln)
        assert "'value'" in line
        assert "'fn'" not in line


class TestPlateauPrompt:
    def test_plateau_prompt_includes_tried_inputs(self):
        from pyct.plugins.llm.prompt import build_plateau_prompt

        prompt = build_plateau_prompt(
            _build_context(inputs_tried=[{"value": 0}, {"value": 5}]),
        )
        assert "0" in prompt
        assert "5" in prompt

    def test_plateau_prompt_references_coverage(self):
        from pyct.plugins.llm.prompt import build_plateau_prompt

        prompt = build_plateau_prompt(
            _build_context(covered_lines=frozenset({1, 2, 3})),
        )
        assert "coverage" in prompt.lower() or "missing" in prompt.lower()


class TestUnknownPrompt:
    def test_unknown_prompt_includes_constraint(self):
        from pyct.plugins.llm.prompt import build_unknown_prompt

        prompt = build_unknown_prompt(_build_context(), "(> value_VAR 10)")
        assert "value_VAR" in prompt
        assert "10" in prompt

    def test_unknown_prompt_includes_target_source(self):
        from pyct.plugins.llm.prompt import build_unknown_prompt

        prompt = build_unknown_prompt(_build_context(), "(> value_VAR 10)")
        assert "def _simple_target" in prompt
