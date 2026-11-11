"""What ``pyct run`` says and reads about the LLM: its flags, and the lines stderr gives.

``pyct.llm`` is imported only once ``--llm`` is given, so a plain run loads no LLM code.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from pyct.config.llm import ALL, DEFAULT_MODEL, PROVIDERS, TOOLS, LlmSettings
from pyct.results.llm_asks import Why
from pyct.run.helpers import Helpers
from pyct.run.llm_seeds import NoSeedError
from pyct.run.notes import AskSkipped, Note, ReplyIgnored, SeedDropped, SeedsKept

if TYPE_CHECKING:
    from pyct.llm.build import Unusable

# the Anthropic ids the help names as examples; pyct keeps no list of ids
ANTHROPIC_EXAMPLES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")


def add_flags(parser: argparse.ArgumentParser) -> None:
    """``--llm TOOLS`` and ``--llm-model PROVIDER:MODEL``."""
    parser.add_argument(
        "--llm",
        dest="llm",
        metavar="TOOLS",
        help=(
            f"switch on LLM tools, joined by commas: {', '.join(TOOLS)}, or {ALL};"
            " the target's code goes to the provider"
        ),
    )
    parser.add_argument(
        "--llm-model",
        dest="llm_model",
        metavar="PROVIDER:MODEL",
        help=(
            f"the model the tools ask; the provider is {' or '.join(PROVIDERS)};"
            f" {DEFAULT_MODEL} by default, or for example anthropic:{ANTHROPIC_EXAMPLES[1]}"
            f" ({', '.join(ANTHROPIC_EXAMPLES)})"
        ),
    )


def start(settings: LlmSettings, own_seeds: int) -> Helpers:
    """The helpers for the run, with the line that says which model the tools ask, or, when the
    LLM cannot be used, no helpers and the line that says why.

    A run with no seed of its own and an LLM it cannot use raises NoSeedError instead, and
    prints nothing here: the refusal is the one line it gives.
    """
    from pyct.llm.build import build

    built = build(settings)
    if built.unusable is None:
        _say(f"llm: {settings.model}, tools: {', '.join(settings.tools)}")
        return built.helpers
    if not own_seeds:
        raise NoSeedError(_unusable_reason(built.unusable))
    _say(f"llm: {_unusable_reason(built.unusable, advice=True)}; running without the LLM")
    return built.helpers


def _unusable_reason(unusable: Unusable, advice: bool = False) -> str:
    """Why the provider cannot be asked; with ``advice``, how to install its missing SDK."""
    provider = unusable.provider
    if unusable.why is Why.NO_KEY:
        return f"no {provider.key}"
    said = f"the {provider.package} package is not installed"
    return f"{said} (pip install '{provider.extra}')" if advice else said


def note_line(note: Note) -> str | None:
    """The stderr line a note gives; None for a note that only labels later traces."""
    match note:
        case AskSkipped(tool, reason):
            return f"llm: {tool} ask skipped: {reason}"
        case ReplyIgnored(tool, reason):
            return f"llm: {tool} reply ignored: {reason}"
        case SeedDropped(number, reason):
            return f"llm: dropped seed {number}: {reason}"
        case SeedsKept():
            return None


def no_seed_line(error: NoSeedError) -> str:
    """The refusal of a run with no seed of its own that the LLM gave none."""
    return f"no seed: the LLM gave none ({error.reason})"


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
