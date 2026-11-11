"""One LLM tool as the connection sees it: its name and its reply's output-token cap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    """A tool's name, as ``--llm`` writes it, and the most tokens its reply may use."""

    name: str
    out_tokens: int
