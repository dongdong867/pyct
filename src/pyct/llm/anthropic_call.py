"""Anthropic's adapter: one user message through the Messages API. Imported only by the worker."""

from __future__ import annotations

import anthropic


def ask(model: str, text: str, out_tokens: int) -> tuple[str, int, int]:
    """The reply's text, its text blocks joined, and its tokens in and out. The SDK reads the
    key and base URL from the environment. No sampling setting is sent; ``max_tokens`` is the
    one setting the API requires."""
    message = anthropic.Anthropic().messages.create(
        model=model,
        max_tokens=out_tokens,
        messages=[{"role": "user", "content": text}],
    )
    reply = "".join(block.text for block in message.content if block.type == "text")
    return reply, message.usage.input_tokens, message.usage.output_tokens
