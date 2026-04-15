"""Unit tests for the LLM plugin's Plugin protocol conformance.

The plugin registers with an engine and exposes three handlers:
``on_seed_request``, ``on_coverage_plateau``, ``on_constraint_unknown``.
A test client is injected via constructor so these tests don't touch
any real LLM API.
"""

from __future__ import annotations


class _StubClient:
    """Test double for the LLM client.

    Records prompts received and returns scripted responses. The
    ``responses`` iterable is consumed left-to-right; each entry is
    the raw text the client would return for the next ``complete``
    call, or ``None`` to simulate a failed call.
    """

    def __init__(self, responses: list[str | None] | None = None):
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if not self.responses:
            return None
        return self.responses.pop(0)


def _build_target_module(tmp_path):
    """Write a target module to ``tmp_path`` and return the loaded function."""
    import importlib.util
    import sys

    src = tmp_path / "sample_target.py"
    src.write_text(
        "def classify(value: int) -> str:\n"
        "    if value > 10:\n"
        "        return 'big'\n"
        "    return 'small'\n"
    )
    spec = importlib.util.spec_from_file_location("sample_target", src)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sample_target"] = module
    spec.loader.exec_module(module)
    return module.classify


def _build_context(target, inputs_tried=(), covered_lines=frozenset()):
    """Construct an EngineContext manually for unit testing."""
    import inspect

    from pyct.config.execution import ExecutionConfig
    from pyct.engine.plugin.context import EngineContext

    return EngineContext(
        iteration=len(inputs_tried),
        constraint_pool=(),
        covered_lines=covered_lines,
        total_lines=4,
        inputs_tried=tuple(inputs_tried),
        target_function=target,
        target_signature=inspect.signature(target),
        config=ExecutionConfig(),
        elapsed_seconds=0.0,
    )


class TestPluginProtocol:
    def test_plugin_satisfies_protocol(self):
        from pyct.engine.plugin.protocol import Plugin
        from pyct.plugins.llm import LLMPlugin

        plugin = LLMPlugin(client=_StubClient())
        assert isinstance(plugin, Plugin)
        assert plugin.name == "llm"
        assert plugin.priority == 50

    def test_plugin_registers_with_engine(self):
        from pyct.config.execution import ExecutionConfig
        from pyct.engine.engine import Engine
        from pyct.plugins.llm import LLMPlugin

        engine = Engine(ExecutionConfig())
        plugin = LLMPlugin(client=_StubClient())
        engine.register(plugin)
        assert plugin in engine.plugins


class TestSeedRequest:
    def test_seed_request_returns_parsed_list_of_dicts(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(
            responses=[
                '[{"value": 0}, {"value": 11}, {"value": -5}]',
            ],
        )
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        seeds = plugin.on_seed_request(ctx)

        assert seeds == [{"value": 0}, {"value": 11}, {"value": -5}]
        assert len(client.prompts) == 1
        assert "classify" in client.prompts[0]

    def test_seed_request_disabled_client_returns_empty(self, tmp_path):
        """A plugin built with a disabled client (no API key) should
        return an empty list — never raise. The engine treats missing
        seeds as a no-op and falls back to the initial args."""
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        plugin = LLMPlugin(client=None)
        ctx = _build_context(target)

        assert plugin.on_seed_request(ctx) == []

    def test_seed_request_parse_failure_returns_empty(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(responses=["this is not python"])
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        assert plugin.on_seed_request(ctx) == []

    def test_seed_request_timeout_returns_empty(self, tmp_path):
        """A client returning None (timeout / API error) must surface
        as an empty seed list, not a crash."""
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(responses=[None])
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        assert plugin.on_seed_request(ctx) == []


class TestCoveragePlateau:
    def test_plateau_returns_seeds_with_missing_lines_in_prompt(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(responses=['[{"value": 42}]'])
        plugin = LLMPlugin(client=client)
        # Simulate plateau: some inputs tried, partial coverage
        ctx = _build_context(
            target,
            inputs_tried=[{"value": 0}, {"value": 5}],
            covered_lines=frozenset({1, 4}),
        )

        seeds = plugin.on_coverage_plateau(ctx)

        assert seeds == [{"value": 42}]
        prompt = client.prompts[0]
        assert "value" in prompt  # tried inputs referenced
        # Prompt should surface missing lines or the partial coverage
        assert "coverage" in prompt.lower() or "missing" in prompt.lower()

    def test_plateau_without_client_returns_empty(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        plugin = LLMPlugin(client=None)
        ctx = _build_context(target)

        assert plugin.on_coverage_plateau(ctx) == []


class TestConstraintUnknown:
    def test_unknown_returns_resolution_dict(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        # For on_constraint_unknown the plugin should return a SINGLE
        # dict (the Resolution), not a list.
        client = _StubClient(responses=['{"value": 13}'])
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        resolution = plugin.on_constraint_unknown(ctx, "(> value_VAR 10)")

        assert resolution == {"value": 13}

    def test_unknown_returns_none_on_parse_failure(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(responses=["garbage"])
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        assert plugin.on_constraint_unknown(ctx, "(> value_VAR 10)") is None

    def test_unknown_returns_none_without_client(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        plugin = LLMPlugin(client=None)
        ctx = _build_context(target)

        assert plugin.on_constraint_unknown(ctx, "(> value_VAR 10)") is None

    def test_unknown_accepts_first_dict_from_list_response(self, tmp_path):
        """LLMs often return a list-of-dicts even when asked for one
        resolution. Accept the first entry to stay useful."""
        from pyct.plugins.llm import LLMPlugin

        target = _build_target_module(tmp_path)
        client = _StubClient(responses=['[{"value": 7}, {"value": 8}]'])
        plugin = LLMPlugin(client=client)
        ctx = _build_context(target)

        assert plugin.on_constraint_unknown(ctx, "(> value_VAR 10)") == {"value": 7}
