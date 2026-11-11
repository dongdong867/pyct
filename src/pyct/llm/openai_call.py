"""OpenAI's adapter: one user message through the Responses API. Imported only by the worker."""

from __future__ import annotations

import openai


def ask(model: str, text: str, out_tokens: int) -> tuple[str, int, int]:
    """The reply's text and its tokens in and out. The SDK reads the key and base URL from the
    environment. Nothing is stored at OpenAI, and no sampling setting is sent."""
    response = openai.OpenAI().responses.create(
        model=model,
        input=[{"role": "user", "content": text}],
        store=False,
        max_output_tokens=out_tokens,
    )
    usage = response.usage
    if usage is None:
        return response.output_text, 0, 0
    return response.output_text, usage.input_tokens, usage.output_tokens
