"""How a run is set up: where its inputs run, and the LLM helpers it may use."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation


@dataclass(frozen=True)
class Setup:
    """Where each input runs (``Isolation``), and the LLM helpers the run may ask.

    One value beside ``Limits`` and ``Tell``, so ``run()`` keeps to five
    parameters as each LLM tool adds a helper. ``Setup()`` runs each input
    in a process of its own and asks no LLM.
    """

    isolation: Isolation = Isolation.AUTO
    helpers: Helpers = field(default_factory=Helpers)
