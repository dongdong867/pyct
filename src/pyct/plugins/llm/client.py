"""LLM client for the plugin — thin wrapper around OpenAI chat completions.

Exposes a minimal ``LLMClient`` protocol (``complete(prompt) -> str | None``)
so tests can inject stubs without touching the real API. The production
client calls OpenAI with a 30-second thread-based timeout and returns
None on any failure — the plugin treats None as "client has nothing to
offer" and falls through to an empty response.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from typing import Any, Protocol

log = logging.getLogger("ct.plugins.llm.client")

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TEMPERATURE = 0.7


class LLMClient(Protocol):
    """Minimal client interface: turn a prompt into text (or None on failure)."""

    def complete(self, prompt: str) -> str | None: ...


class OpenAIClient:
    """Production client that calls OpenAI chat completions.

    Returns None on missing API key, timeout, or any error — never raises.
    The 30s timeout is enforced by a daemon thread rather than the OpenAI
    SDK's own timeout because we want a hard deadline regardless of the
    SDK's retry behavior.

    Token usage is accumulated across all ``complete()`` calls and
    accessible via ``get_stats()`` for benchmark reporting.
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._input_tokens: int = 0
        self._output_tokens: int = 0

    def complete(self, prompt: str) -> str | None:
        container: dict[str, Any] = {"text": None, "error": None}

        def _call() -> None:
            try:
                container["text"] = self._raw_call(prompt)
            except Exception as exc:  # noqa: BLE001 — client never raises to caller
                container["error"] = exc

        thread = threading.Thread(target=_call, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)

        if thread.is_alive():
            log.warning("LLM call timed out after %ss", self._timeout)
            return None
        if container["error"] is not None:
            log.warning("LLM call failed: %s", container["error"])
            return None
        return container["text"]

    def _raw_call(self, prompt: str) -> str | None:
        try:
            from openai import OpenAI  # pyrefly: ignore[missing-import]  # optional dep
        except ImportError:
            log.warning("openai package not installed — LLM plugin disabled")
            return None

        client = OpenAI(api_key=self._api_key, timeout=self._timeout, max_retries=1)
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a test generation expert for concolic "
                            "testing. Return only the requested format with "
                            "literal values. Never reference names or "
                            "constants from the code under test."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            if response.usage is not None:
                self._input_tokens += response.usage.prompt_tokens
                self._output_tokens += response.usage.completion_tokens
            return response.choices[0].message.content
        finally:
            with contextlib.suppress(Exception):  # best-effort cleanup
                client.close()

    def get_stats(self) -> dict[str, int]:
        """Return accumulated token usage across all calls."""
        return {
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
        }


def build_default_client() -> LLMClient | None:
    """Return a production client if OPENAI_API_KEY is set, else None.

    None is a valid client value for the plugin — the plugin's handlers
    all check ``self._client is None`` and return empty/None, so the
    engine runs unchanged when the API key is missing.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAIClient(api_key=api_key)
