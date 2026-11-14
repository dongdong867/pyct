"""The LLM a run uses, built from its settings: the helpers, or why the LLM cannot be used."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

from pyct.config.llm import LlmSettings, Model
from pyct.llm.caller import Caller, WorkerCaller
from pyct.llm.connection import Connection
from pyct.llm.ledger import Ledger
from pyct.llm.providers import PROVIDERS, Provider
from pyct.llm.recording import Recording
from pyct.llm.replay import ReplayCaller, read_replay
from pyct.llm.rewrites import REWRITES, LlmRewrites
from pyct.llm.seeds import SEEDS, LlmSeeds
from pyct.llm.summaries import SUMMARIES, LlmSummaries
from pyct.results.llm_asks import Why
from pyct.run.helpers import Helpers
from pyct.run.tell import Noted


@dataclass(frozen=True)
class Unusable:
    """Why the run cannot ask its provider, found before any ask: its SDK is not installed, or
    its key variable is unset or empty."""

    why: Why
    provider: Provider


@dataclass(frozen=True)
class Built:
    """The helpers for the run and the model they ask, with the connection they ask through,
    or, when the LLM cannot be used, no helpers, no connection and why.

    A replay's model is the one its recording names.
    """

    helpers: Helpers
    model: Model
    connection: Connection | None = None
    unusable: Unusable | None = None


def build(settings: LlmSettings, noted: Noted | None = None) -> Built:
    """The helpers the switched-on tools give, asking through one connection for the run, which
    records every reply in a new file and refuses asks past ``settings.limit``, said once
    through ``noted``.

    With ``settings.replay`` the recording answers instead of the model, so it needs no key and
    no SDK; a recording that cannot be read raises UsageError. Otherwise it checks only that
    the SDK's package can be found, which imports nothing, then that the key variable is set
    and not empty; it never reads the key's value.
    """
    if settings.replay is not None:
        replay = read_replay(settings.replay)
        return _built(settings, replay.model, ReplayCaller(replay), noted)
    provider = PROVIDERS[settings.model.provider]
    if importlib.util.find_spec(provider.package) is None:
        return Built(Helpers(), settings.model, unusable=Unusable(Why.NO_PACKAGE, provider))
    if not os.environ.get(provider.key):
        return Built(Helpers(), settings.model, unusable=Unusable(Why.NO_KEY, provider))
    return _built(settings, settings.model, WorkerCaller(settings.model), noted)


def _built(settings: LlmSettings, model: Model, caller: Caller, noted: Noted | None) -> Built:
    """One connection over ``caller``, with the run's ledger and a new recording, and each
    switched-on tool on it."""
    recording = Recording.start(model, settings.tools)
    connection = Connection(caller, recording, Ledger(settings.limit), noted)
    tools = settings.tools
    helpers = Helpers(
        seeds=LlmSeeds(connection) if SEEDS.name in tools else None,
        summaries=LlmSummaries(connection) if SUMMARIES.name in tools else None,
        rewrites=LlmRewrites(connection) if REWRITES.name in tools else None,
    )
    return Built(helpers, model, connection)
