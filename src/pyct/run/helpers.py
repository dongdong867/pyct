"""The LLM helpers a run may use. ``Helpers()`` with nothing set is a plain concolic run."""

from __future__ import annotations

from dataclasses import dataclass

from pyct.rewrite.provider import RewriteProvider
from pyct.run.llm_seeds import SeedProvider


@dataclass(frozen=True)
class Helpers:
    """One field per LLM tool, each None by default. A helper never changes the tree and never
    reads engine state.

    ``seeds`` is asked once, before the first input, for seeds that run after the user's own.
    ``rewrites`` is asked at a stuck moment for an easier condition in place of one whose
    asks ran out (``pyct.run.rewrites``).
    """

    seeds: SeedProvider | None = None
    rewrites: RewriteProvider | None = None
