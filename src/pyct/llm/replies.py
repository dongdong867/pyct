"""Reading a model's reply: helpers every tool can use."""

from __future__ import annotations

import json

_DECODER = json.JSONDecoder()


def json_items(text: str) -> tuple[str, ...] | None:
    """Each item of the first JSON array in ``text``, as its own JSON text, so each can be
    checked alone. None when no ``[`` in the text starts an array Python's JSON reader reads:
    not JSON, nested too deep, or holding a number too long to read."""
    start = text.find("[")
    while start != -1:
        try:
            value, _ = _DECODER.raw_decode(text, start)
        except (ValueError, RecursionError):
            value = None
        if isinstance(value, list):
            return tuple(json.dumps(item) for item in value)
        start = text.find("[", start + 1)
    return None
