"""The LLM helpers a run may use. ``Helpers()`` with nothing set is a plain concolic run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Helpers:
    """One field per LLM tool, each None by default. A helper never changes the tree and never
    reads engine state."""
