"""The seeds ask: the request ``run()`` sends before its first input, and what it does with the
reply. Each seed is read and checked as a ``--seeds`` line is, then kept, or dropped and said.
One that names a class with ``"__class__"`` is dropped before the checks: checking it would
import the module it names in pyct's process, which never runs reply text.

``SeedProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.seeds``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyct.binding.builds import CLASS_KEY
from pyct.config.command_line import UsageError
from pyct.config.goal import Goal
from pyct.config.llm import SEEDS_TOOL
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.code_context import code_context
from pyct.run.notes import AskSkipped, ReplyIgnored, SeedDropped, SeedsKept
from pyct.run.seed_checks import SeedCheck, parse_seed
from pyct.run.target import Target
from pyct.run.tell import Told

# the most seeds one reply may give; the request asks for at most this many
MOST_SEEDS = 5
# the user's seeds a request quotes at most, and the characters of JSON each may take
QUOTED_SEEDS = 10
QUOTED_SEED_SIZE = 2_000
# why an LLM seed that names a class is dropped: the checks would import the module it names
# in pyct's process, and pyct's process never runs reply text
NAMES_A_CLASS = f'an LLM seed names no class with "{CLASS_KEY}"'
# why a reply whose array is empty gives no seed
NO_SEED = "the reply held no seed"


class NoSeedError(Exception):
    """A run with no seed of its own got none from the LLM either; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SeedRequest:
    """What a seeds ask is about: the place, the target's spec; the target's code and its
    same-package callees' (``code_context``); its signature as Python writes it; the user's
    seeds as JSON; and the goal the seeds are for."""

    place: str
    code: str
    signature: str
    seeds: tuple[str, ...]
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
        told.note(AskSkipped(SEEDS_TOOL, answer.reason))
        return _none_left(own, answer.reason, waited)
    if answer.ignored is not None or not answer.items:
        ignored = answer.ignored or NO_SEED
        told.note(ReplyIgnored(SEEDS_TOOL, ignored))
        return _none_left(own, ignored, waited)
    kept = _kept(SeedCheck.of(target), own, answer.items, told)
    if kept:
        told.note(SeedsKept(tuple(number for number, _ in kept)))
    seeds = tuple(seed for _, seed in kept)
    if not seeds and not own:
        raise NoSeedError("every seed was dropped")
    return AskedSeeds(seeds, waited)


def _none_left(own: Sequence[Mapping[str, object]], reason: str, waited: float) -> AskedSeeds:
    """No seed from the LLM: refused with ``reason`` when the run has none of its own."""
    if not own:
        raise NoSeedError(reason)
    return AskedSeeds((), waited)


def seed_request(target: Target, own: Sequence[Mapping[str, object]], goal: Goal) -> SeedRequest:
    """The request for ``target``, quoting at most ``QUOTED_SEEDS`` of the user's seeds and none
    whose JSON is longer than ``QUOTED_SEED_SIZE`` or that JSON cannot write."""
    written = [_json(seed) for seed in own]
    quoted = tuple(text for text in written if text is not None and len(text) <= QUOTED_SEED_SIZE)[
        :QUOTED_SEEDS
    ]
    return SeedRequest(
        place=target.spec,
        code=code_context(target),
        signature=str(target.signature),
        seeds=quoted,
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
    repeat names the first input it repeats by its stdout line. The user's seeds run first, so
    the LLM's kept seeds are numbered after them.
    """
    inputs: dict[str, int] = {}
    for number, seed in enumerate(own, start=1):
        written = _json(seed)
        if written is not None:
            inputs.setdefault(written, number)
    kept: list[tuple[int, Mapping[str, object]]] = []
    for number, text in enumerate(items, start=1):
        reason, seed = _judged(check, inputs, number, text)
        if seed is None:
            told.note(SeedDropped(number, reason))
            continue
        kept.append((number, seed))
        inputs[json.dumps(seed)] = len(own) + len(kept)
    return kept


def _judged(
    check: SeedCheck, inputs: Mapping[str, int], number: int, text: str
) -> tuple[str, Mapping[str, object] | None]:
    """The seed an item writes, or why it is dropped: past the fifth, its shape as JSON, a class
    it names, a check's reasons joined by ``; ``, or the input it repeats."""
    if number > MOST_SEEDS:
        return f"more than {MOST_SEEDS} seeds", None
    try:
        seed = parse_seed(text)
    except UsageError as error:
        return str(error), None
    if _names_class(seed):
        return NAMES_A_CLASS, None
    reasons = check.refusals(seed)
    if reasons:
        return "; ".join(reasons), None
    repeated = inputs.get(json.dumps(seed))
    if repeated is not None:
        return f"same seed as input {repeated}", None
    return "", seed


def _names_class(value: object) -> bool:
    """Whether a JSON value holds a ``"__class__"`` key at any depth, read in a loop, not a call
    per level, so a seed as deep as the checks take is read too."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if CLASS_KEY in item:
                return True
            item = list(item.values())
        if isinstance(item, list):
            pending.extend(item)
    return False


def _json(seed: Mapping[str, object]) -> str | None:
    """The seed as JSON, or None when it holds a value JSON cannot write, such as an object."""
    try:
        return json.dumps(seed)
    except (TypeError, ValueError):
        return None
