"""What ``pyct run`` says and reads about the LLM: its flags, and the lines stderr gives.

``pyct.llm`` is imported only once ``--llm`` is given, so a plain run loads no LLM code.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyct.config.llm import ALL, DEFAULT_LIMIT, DEFAULT_MODEL, PROVIDERS, TOOLS, LlmSettings
from pyct.results.llm_asks import LlmUse, Why
from pyct.run.helpers import Helpers
from pyct.run.llm_seeds import NoSeedError
from pyct.run.notes import AskSkipped, LimitReached, Note, ReplyIgnored, SeedDropped, SeedsKept
from pyct.run.tell import Noted

if TYPE_CHECKING:
    from pyct.llm.build import Built, Unusable

# the Anthropic ids the help names as examples; pyct keeps no list of ids
ANTHROPIC_EXAMPLES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")


def add_flags(parser: argparse.ArgumentParser) -> None:
    """``--llm TOOLS``, ``--llm-model PROVIDER:MODEL``, ``--llm-replay FILE`` and
    ``--llm-limit TOKENS``."""
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
    _add_spending_flags(parser)


def _add_spending_flags(parser: argparse.ArgumentParser) -> None:
    """``--llm-replay FILE``, which spends no tokens, and ``--llm-limit TOKENS``."""
    parser.add_argument(
        "--llm-replay",
        dest="llm_replay",
        metavar="FILE",
        help=(
            "answer each ask from a recording a run made, by its tool, place and try, and ask no"
            " model; the run reports the recording's model"
        ),
    )
    parser.add_argument(
        "--llm-limit",
        dest="llm_limit",
        metavar="TOKENS",
        help=(
            f"the tokens in and out together the run may spend on the LLM; {DEFAULT_LIMIT:,} by"
            " default. A replay counts each reply at its recorded tokens"
        ),
    )


@dataclass(frozen=True)
class Started:
    """The helpers for the run, the line stderr gives before the first input, and what was
    built, which the closing lines read once the run ends."""

    helpers: Helpers
    said: str
    built: Built
    tools: tuple[str, ...]

    def use(self) -> LlmUse:
        """What the tools did, for the summary line: zero counts when the LLM could not be used,
        so a reader sees the switch was on."""
        connection = self.built.connection
        if connection is None:
            return LlmUse(str(self.built.model), self.tools)
        return connection.ledger.use(self.built.model, self.tools)

    def closing(self) -> tuple[str, ...]:
        """The lines that end stderr's run summary: the counts, then where the replies were
        recorded, or why they were not. None when the LLM could not be used."""
        connection = self.built.connection
        if connection is None or connection.recording is None:
            return ()
        recording = connection.recording
        if recording.path is None:
            where = f"llm: replies not recorded ({recording.failure})"
        else:
            where = f"llm: replies recorded in {recording.path}"
        return counts_line(self.use()), where


def counts_line(use: LlmUse) -> str:
    """The asks, the tokens spent in this run, and the seconds waited, to the tenth."""
    return (
        f"llm: {use.asks} asks, {use.replayed} replayed, {use.skipped} skipped,"
        f" {use.tokens_in} tokens in, {use.tokens_out} out, {use.seconds:.1f} s waiting"
    )


def start(settings: LlmSettings, own_seeds: int, noted: Noted | None) -> Started:
    """The helpers for the run, with the line that says which model the tools ask, a replay's
    the one its recording names, or, when the LLM cannot be used, no helpers and the line that
    says why.

    A run with no seed of its own and an LLM it cannot use raises NoSeedError instead: the
    refusal is the one line it gives. A replay file that cannot be read raises UsageError.
    ``noted`` hears the connection's notes, such as the limit reached.
    """
    from pyct.llm.build import build

    built = build(settings, noted)
    if built.unusable is None:
        said = f"llm: {built.model}, tools: {', '.join(settings.tools)}"
        return Started(built.helpers, said, built, settings.tools)
    if not own_seeds:
        raise NoSeedError(_unusable_reason(built.unusable))
    said = f"llm: {_unusable_reason(built.unusable, advice=True)}; running without the LLM"
    return Started(built.helpers, said, built, settings.tools)


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
        case LimitReached():
            return "llm: token limit reached; no more asks"
        case SeedsKept():
            return None


def no_seed_line(error: NoSeedError) -> str:
    """The refusal of a run with no seed of its own that the LLM gave none."""
    return f"no seed: the LLM gave none ({error.reason})"
