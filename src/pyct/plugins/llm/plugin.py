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
from enum import StrEnum
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


class LLMPoint(StrEnum):
    """A logical LLM integration point that can be enabled independently.

    Each point maps to one or more event handlers:

    * ``SEED`` → ``on_seed_request``
    * ``SOLVER_FAILURE`` → ``on_constraint_unknown``
    * ``PLATEAU`` → both ``on_coverage_plateau`` and
      ``on_post_loop_discovery`` — plateau discovery is one component
      with two trigger sites (in-loop stall and post-loop push).

    A point absent from a plugin's ``enabled_points`` silences its
    handler(s): they return the empty/None no-op without calling the
    LLM. This is what the single-component ablation runners use to
    isolate each point's contribution.
    """

    SEED = "seed"
    PLATEAU = "plateau"
    SOLVER_FAILURE = "solver_failure"


_ALL_POINTS: frozenset[LLMPoint] = frozenset(LLMPoint)


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
        enabled_points: frozenset[LLMPoint] = _ALL_POINTS,
    ) -> None:
        if client is _DEFAULT_CLIENT:
            client = build_default_client()
        self._client: LLMClient | None = client  # type: ignore[assignment]
        # Integration points this plugin responds to. A point not in the
        # set silences its handler(s) before any LLM call. Defaults to
        # all points, so an unparameterized plugin behaves as before.
        self._enabled_points: frozenset[LLMPoint] = enabled_points
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

    def _active(self, point: LLMPoint) -> bool:
        """True when a client exists and ``point`` is enabled.

        When False, the calling handler must degrade to its empty/None
        no-op without contacting the LLM.
        """
        return self._client is not None and point in self._enabled_points

    def on_seed_request(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if not self._active(LLMPoint.SEED):
            return []
        prompt = build_seed_prompt(ctx)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_coverage_plateau(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if not self._active(LLMPoint.PLATEAU):
            return []
        prompt = build_plateau_prompt(ctx)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_post_loop_discovery(self, ctx: EngineContext) -> list[dict[str, Any]]:
        if not self._active(LLMPoint.PLATEAU):
            return []
        prompt = build_plateau_prompt(ctx)
        content = self._client.complete(prompt)
        return self._parse_and_count(content)

    def on_constraint_unknown(
        self,
        ctx: EngineContext,
        constraint: Any,
    ) -> dict[str, Any] | None:
        if not self._active(LLMPoint.SOLVER_FAILURE):
            return None
        prompt = build_unknown_prompt(ctx, constraint)
        content = self._client.complete(prompt)
        return parse_single_input(content)
