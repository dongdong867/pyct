"""LLM plugin — routes engine events through an LLM client.

Implements three event handlers:

* ``on_seed_request`` — collector event fired once at the start of
  exploration. Returns a list of seed inputs generated from the
  target's source code.
* ``on_coverage_plateau`` — collector event fired when exploration
  stalls. Returns more inputs aimed at the uncovered branches.
* ``on_post_loop_discovery`` — collector event fired after the main
  exploration loop ends, to close remaining coverage gaps. Reuses the
  plateau prompt (same "cover these uncovered lines" intent).
* ``on_constraint_unknown`` — resolver event fired when the solver
  returns UNKNOWN/ERROR on a constraint. Returns a single
  ``Resolution`` dict or ``None``.

All handlers degrade to empty/None when the client is missing or
the LLM returns malformed output. Engine exploration is unaffected.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pyct.plugins.llm.client import LLMClient, build_default_client
from pyct.plugins.llm.parser import parse_input_list, parse_single_input
from pyct.plugins.llm.prompt import (
    PromptContextOptions,
    build_plateau_prompt,
    build_seed_prompt,
    build_unknown_prompt,
)

if TYPE_CHECKING:
    from pyct.engine.plugin.context import EngineContext

log = logging.getLogger("ct.plugins.llm")

_NAME = "llm"
_PRIORITY = 50
_DEFAULT_CLIENT = object()  # sentinel: "caller did not specify a client"


class LLMPlugin:
    """Engine plugin that delegates seeding, plateau recovery, and solver
    fallback to an LLM client.

    Clients are injected so tests can substitute a stub. In production,
    ``build_default_client()`` returns an ``OpenAIClient`` wrapping the
    OpenAI chat completions API when ``OPENAI_API_KEY`` is set. When
    the key is missing, the client is ``None`` and every handler
    degrades to a safe empty/None response — the plugin registers
    cleanly but contributes nothing.
    """

    name: str = _NAME
    priority: int = _PRIORITY

    def __init__(
        self,
        client: LLMClient | None | object = _DEFAULT_CLIENT,
        context_options: PromptContextOptions | None = None,
    ) -> None:
        if client is _DEFAULT_CLIENT:
            client = build_default_client()
        self._client: LLMClient | None = client  # type: ignore[assignment]
        # Static-analysis blocks the seed prompt carries. None keeps the
        # source-only prompt the engine shipped.
        self._context_options = context_options
        # Accumulated parse-fail count across every list-parsing handler.
        # The engine sweeps registered plugins for this attribute when
        # building its result so the count surfaces on
        # ``ExplorationResult.gen_parse_failed`` without changing the
        # plugin protocol's return shape.
        self.parse_failed: int = 0

    def _parse_and_count(self, content: str | None) -> list[dict[str, Any]]:
        """Parse a response into inputs while accumulating ``parse_failed``."""
        inputs, fails = parse_input_list(content)
        self.parse_failed += fails
        return inputs

    def on_seed_request(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        prompt = build_seed_prompt(ctx, self._context_options)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_coverage_plateau(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        prompt = build_plateau_prompt(ctx)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_post_loop_discovery(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        prompt = build_plateau_prompt(ctx)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_constraint_unknown(
        self,
        ctx: EngineContext,
        constraint: Any,
    ) -> dict[str, Any] | None:
        if self._client is None:
            return None
        prompt = build_unknown_prompt(ctx, constraint)
        content = self._client.complete(prompt)
        return parse_single_input(content)
