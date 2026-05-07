"""Acceptance tests: ``gen_parse_failed`` counter.

The engine surfaces a ``gen_parse_failed`` counter on every result —
the sum of every registered plugin's ``parse_failed`` instance attribute
at the moment the result is built. Plugins that don't expose
``parse_failed`` contribute zero (the engine falls back via
``getattr(p, "parse_failed", 0)``).

This is the third leg of the LLM diagnostic surface: ``gen_unsat`` and
``gen_unknown`` count solver outcomes, ``gen_parse_failed`` counts
parser drops on LLM responses. Together they let a benchmark consumer
distinguish "solver gave up" from "LLM produced unparseable output".
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine


def _two_branch(x: int) -> int:
    if x > 10:
        return 1
    return 0


class _PluginWithParseFailed:
    """Bare plugin that pre-sets ``parse_failed`` so the engine can sweep it."""

    name = "stub_with_parse_failed"
    priority = 100

    def __init__(self, parse_failed: int) -> None:
        self.parse_failed = parse_failed

    def on_seed_request(self, ctx: Any) -> list[dict[str, Any]]:  # noqa: ARG002
        return []


class _PluginWithoutAttr:
    name = "stub_no_attr"
    priority = 100

    def on_seed_request(self, ctx: Any) -> list[dict[str, Any]]:  # noqa: ARG002
        return []


class TestGenParseFailedFromPluginSweep:
    """Engine sums every registered plugin's ``parse_failed`` attribute."""

    def test_no_plugins_keeps_counter_zero(self):
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_parse_failed == 0

    def test_single_plugin_with_parse_failed_attr_propagates(self):
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_PluginWithParseFailed(parse_failed=4))
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_parse_failed == 4

    def test_multiple_plugins_sum_their_parse_failed(self):
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_PluginWithParseFailed(parse_failed=2))
        engine.register(_PluginWithParseFailed(parse_failed=3))
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_parse_failed == 5

    def test_plugin_without_attr_contributes_zero(self):
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_PluginWithParseFailed(parse_failed=2))
        engine.register(_PluginWithoutAttr())
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_parse_failed == 2


class TestGenParseFailedReflectsLLMPluginActivity:
    """Drive the real LLMPlugin via a stub client; verify end-to-end flow."""

    def test_unparseable_seed_response_counts_as_one(self, tmp_path):
        from pyct.plugins.llm import LLMPlugin

        class _StubClient:
            def __init__(self, responses):
                self.responses = list(responses)

            def complete(self, prompt: str) -> str | None:  # noqa: ARG002
                return self.responses.pop(0) if self.responses else None

        config = ExecutionConfig(max_iterations=3, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(LLMPlugin(client=_StubClient(responses=["garbage"])))
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_parse_failed >= 1
