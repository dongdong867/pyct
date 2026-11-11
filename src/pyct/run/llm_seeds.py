"""The seeds ask: the request ``run()`` sends before its first input, and what it does with the
reply. Each seed is read and checked as a ``--seeds`` line is, then kept, or dropped and said.

``SeedProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.seeds``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyct.config.goal import Goal
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.code_context import code_context
from pyct.run.notes import AskSkipped, ReplyIgnored, SeedDropped, SeedsKept
from pyct.run.seed_checks import SeedCheck
from pyct.run.target import Target
from pyct.run.tell import Told

# the tool's name, as stderr and the switch write it
TOOL = "seeds"
# the most seeds one reply may give; the request asks for at most this many
MOST_SEEDS = 5
# the user's seeds a request quotes at most, and the characters of JSON each may take
QUOTED_SEEDS = 10
QUOTED_SEED_SIZE = 2_000


class NoSeedError(Exception):
    """A run with no seed of its own got none from the LLM either; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SeedRequest:
    """What a seeds ask is about: the place, the target's spec; the target's code and its
    same-package callees' (``code_context``); its signature as Python writes it; the user's
    seeds as JSON; the parameter that holds a method's constructor arguments, if any; and the
    goal the seeds are for."""

    place: str
    code: str
    signature: str
    seeds: tuple[str, ...]
    self_name: str | None = None
    goal: Goal = Goal.COVERAGE


@dataclass(frozen=True)
class SeedReply:
    """The reply's seeds, each array item as its own JSON text, so each is checked alone.

    ``ignored`` says why the reply held nothing the tool could read, such as no JSON array.
    """

    items: tuple[str, ...]
    cost: AskCost
    ignored: str | None = None


class SeedProvider(Protocol):
    """Gives seeds for a target. It never raises for an LLM problem: it returns Unanswered."""

    def seeds(self, request: SeedRequest) -> SeedReply | Unanswered: ...


@dataclass(frozen=True)
class AskedSeeds:
    """The LLM's seeds that passed, in reply order, and the seconds pyct waited for them."""

    seeds: tuple[Mapping[str, object], ...]
    waited: float


def ask_seeds(
    provider: SeedProvider,
    target: Target,
    own: Sequence[Mapping[str, object]],
    goal: Goal,
    told: Told,
) -> AskedSeeds:
    """Ask once for seeds, keep the ones that pass, and say each drop and the kept places.

    The wait is measured around the provider's call alone; building the request and checking
    the seeds are pyct's own work. A run with no seed of its own that keeps none raises
    NoSeedError.
    """
    request = seed_request(target, own, goal)
    started = time.monotonic()
    answer = provider.seeds(request)
    waited = time.monotonic() - started
    if isinstance(answer, Unanswered):
        told.note(AskSkipped(TOOL, answer.reason))
        return _none_left(own, answer.reason, waited)
    if answer.ignored is not None:
        told.note(ReplyIgnored(TOOL, answer.ignored))
        return _none_left(own, answer.ignored, waited)
    kept = _kept(SeedCheck.of(target), own, answer.items, told)
    if kept:
        told.note(SeedsKept(tuple(number for number, _ in kept)))
    seeds = tuple(seed for _, seed in kept)
    if not seeds and not own:
        raise NoSeedError("every seed was dropped" if answer.items else "the reply held no seed")
    return AskedSeeds(seeds, waited)


def _none_left(own: Sequence[Mapping[str, object]], reason: str, waited: float) -> AskedSeeds:
    """No seed from the LLM: refused with ``reason`` when the run has none of its own."""
    if not own:
        raise NoSeedError(reason)
    return AskedSeeds((), waited)


def seed_request(target: Target, own: Sequence[Mapping[str, object]], goal: Goal) -> SeedRequest:
    """The request for ``target``, quoting at most ``QUOTED_SEEDS`` of the user's seeds and none
    whose JSON is longer than ``QUOTED_SEED_SIZE``."""
    written = [json.dumps(seed) for seed in own]
    quoted = tuple(text for text in written if len(text) <= QUOTED_SEED_SIZE)[:QUOTED_SEEDS]
    return SeedRequest(
        place=target.spec,
        code=code_context(target),
        signature=str(target.signature),
        seeds=quoted,
        self_name=target.self_name,
        goal=goal,
    )


def _kept(
    check: SeedCheck,
    own: Sequence[Mapping[str, object]],
    items: Sequence[str],
    told: Told,
) -> list[tuple[int, Mapping[str, object]]]:
    """Each item that passes the checks and repeats no earlier seed, with its place in the
    reply from 1. Each other item is dropped, said with its reason.

    Two seeds are the same when they write the same JSON, as ``--seeds`` reads repeats; a
    repeat names the input it repeats by its stdout line.
    """
    inputs = {json.dumps(seed): number for number, seed in enumerate(own, start=1)}
    kept: list[tuple[int, Mapping[str, object]]] = []
    for number, text in enumerate(items, start=1):
        reason, seed = _judged(check, inputs, number, text)
        if seed is None:
            told.note(SeedDropped(number, reason))
            continue
        inputs[json.dumps(seed)] = len(inputs) + 1
        kept.append((number, seed))
    return kept


def _judged(
    check: SeedCheck, inputs: Mapping[str, int], number: int, text: str
) -> tuple[str, Mapping[str, object] | None]:
    """The seed an item writes, or why it is dropped: past the fifth, a check's reasons joined
    by ``; ``, or the input it repeats."""
    if number > MOST_SEEDS:
        return f"more than {MOST_SEEDS} seeds", None
    seed, reasons = check.read(text)
    if seed is None:
        return "; ".join(reasons), None
    repeated = inputs.get(json.dumps(seed))
    if repeated is not None:
        return f"same seed as input {repeated}", None
    return "", seed
