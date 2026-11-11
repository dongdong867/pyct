"""The LLM a run uses, built from its settings: the helpers, or why the LLM cannot be used."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

from pyct.config.llm import LlmSettings
from pyct.llm.caller import WorkerCaller
from pyct.llm.connection import Connection
from pyct.llm.providers import PROVIDERS, Provider
from pyct.llm.seeds import LlmSeeds
from pyct.results.llm_asks import Why
from pyct.run.helpers import Helpers


@dataclass(frozen=True)
class Unusable:
    """Why the run cannot ask its provider, found before any ask: its SDK is not installed, or
    its key variable is unset or empty."""

    why: Why
    provider: Provider


@dataclass(frozen=True)
class Built:
    """The helpers for the run, or, when the LLM cannot be used, none and why."""

    helpers: Helpers
    unusable: Unusable | None = None


def build(settings: LlmSettings) -> Built:
    """The helpers the switched-on tools give, asking through one connection for the run.

    It checks only that the SDK's package can be found, which imports nothing, then that the
    key variable is set and not empty; it never reads the key's value.
    """
    provider = PROVIDERS[settings.model.provider]
    if importlib.util.find_spec(provider.package) is None:
        return Built(Helpers(), Unusable(Why.NO_PACKAGE, provider))
    if not os.environ.get(provider.key):
        return Built(Helpers(), Unusable(Why.NO_KEY, provider))
    connection = Connection(WorkerCaller(settings.model))
    seeds = LlmSeeds(connection) if "seeds" in settings.tools else None
    return Built(Helpers(seeds=seeds))
