"""LLM plugin — routes engine events through an LLM client.

Implements three event handlers:

* ``on_seed_request`` — collector event fired once at the start of
  exploration. Returns a list of seed inputs generated from the
  target's source code.
* ``on_coverage_plateau`` — collector event fired when exploration
  stalls. Returns more inputs aimed at the uncovered branches.
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

    def __init__(self, client: LLMClient | None | object = _DEFAULT_CLIENT) -> None:
        if client is _DEFAULT_CLIENT:
            client = build_default_client()
        self._client: LLMClient | None = client  # type: ignore[assignment]

    def on_seed_request(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        prompt = build_seed_prompt(ctx)
        content = self._client.complete(prompt)
        return parse_input_list(content)

    def on_coverage_plateau(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        prompt = build_plateau_prompt(ctx)
        content = self._client.complete(prompt)
        return parse_input_list(content)

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
