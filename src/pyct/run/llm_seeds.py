"""The seeds ask: the request ``run()`` sends before its first input, and what it does with the
reply. Each seed is read and checked as a ``--seeds`` line is, then kept, or dropped and said.
Before the checks, which import the module a ``"__class__"`` names in pyct's process, each class
it names must be of the user's own code, in a module the request listed or one already imported
(``ClassGate``).

``SeedProvider`` is declared here, at its consumer, and implemented in ``pyct.llm.seeds``.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyct.binding.classes import (
    ClassFormError,
    Unread,
    class_parts,
    is_a_class,
    module_of,
    plain_attribute,
    written,
)
from pyct.binding.places import step_in
from pyct.binding.seed_keys import CLASS_KEY
from pyct.config.command_line import UsageError
from pyct.config.goal import Goal
from pyct.config.llm import SEEDS_TOOL
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.class_listing import class_listing, user_module
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
# why an LLM seed's class is refused, in the lines that quote the name: a library's, one in a
# module the request did not list and that was not imported, or a name with a module among its
# steps after ::
NOT_THE_USER_S = "must name a class of the user's own code, got"
NOT_LISTED = "must name a class the request listed or one already imported, got"
THROUGH_A_MODULE = "must not step through a module, got"
QUOTING = (NOT_THE_USER_S, NOT_LISTED, THROUGH_A_MODULE)
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
    seeds as JSON; the goal the seeds are for; and the classes of the target module's folder
    (``class_listing``), empty when it defines none."""

    place: str
    code: str
    signature: str
    seeds: tuple[str, ...]
    goal: Goal = Goal.COVERAGE
    classes: str = ""


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
    listing = class_listing(target.spec.partition("::")[0])
    request = seed_request(target, own, goal, listing.text)
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
    gate = ClassGate(target.home, listing.modules)
    kept = _kept(SeedCheck.of(target), gate, own, answer.items, told)
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


def seed_request(
    target: Target, own: Sequence[Mapping[str, object]], goal: Goal, classes: str
) -> SeedRequest:
    """The request for ``target``, quoting at most ``QUOTED_SEEDS`` of the user's seeds and none
    whose JSON is longer than ``QUOTED_SEED_SIZE`` or that JSON cannot write, with the classes
    ``class_listing`` wrote."""
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
        classes=classes,
    )


def _kept(
    check: SeedCheck,
    gate: ClassGate,
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
        reason, seed = _judged(check, gate, inputs, number, text)
        if seed is None:
            told.note(SeedDropped(number, reason))
            continue
        kept.append((number, seed))
        inputs[json.dumps(seed)] = len(own) + len(kept)
    return kept


def _judged(
    check: SeedCheck, gate: ClassGate, inputs: Mapping[str, int], number: int, text: str
) -> tuple[str, Mapping[str, object] | None]:
    """The seed an item writes, or why it is dropped: past the fifth, its shape as JSON, the
    classes it names (``ClassGate``), then the seed checks, each one's reasons joined by ``; ``,
    or the input it repeats."""
    if number > MOST_SEEDS:
        return f"more than {MOST_SEEDS} seeds", None
    try:
        seed = parse_seed(text)
    except UsageError as error:
        return str(error), None
    reasons = gate.refusals(seed) or check.refusals(seed)
    if reasons:
        return "; ".join(reasons), None
    repeated = inputs.get(json.dumps(seed))
    if repeated is not None:
        return f"same seed as input {repeated}", None
    return "", seed


@dataclass(frozen=True)
class ClassGate:
    """The classes an LLM seed may name with ``"__class__"``: a class of the user's own code, in
    a module the request listed or one already imported.

    ``home`` is the module a bare name is read in. ``listed`` is the
    modules whose classes the request listed. A module is the user's code
    as ``user_module`` tells it, the rule the listing follows too, so a
    library's module is refused also when the target is inside it.
    """

    home: str
    listed: frozenset[str]

    def refusals(self, seed: Mapping[str, object]) -> list[str]:
        """A line for each ``"__class__"`` str at any depth of ``seed`` that names a class an LLM
        seed may not, outer before inner in seed order.

        Its module is tested by name before anything imports it. A module
        that passes is imported, and the name's steps are read in it with
        ``plain_attribute``, which runs no code of the module's or a class's.
        Each step must reach a class whose own module is the user's code,
        the last step too; ``load_class`` then reads each such step the same
        way, to the same class. A module, a step that reaches a module, and
        a library's class are refused in lines that quote the name after
        ``, got``. A step that is missing, one that is not a class, and one
        that cannot be read without running code are refused in
        ``place: reason`` lines, as the seed checks write them. A value that
        is not a str and one badly written pass, and the seed checks report
        them. A module that fails to import is left to the seed checks too,
        and the gate reads none of that name's steps: the seed checks report
        a module that fails again, and build from one whose next import works.
        """
        return [line for place, text in _class_names(seed) for line in self._lines(place, text)]

    def _lines(self, place: str, text: str) -> list[str]:
        """The line for the ``"__class__"`` ``text`` of the object at ``place``, or none."""
        try:
            module_name, qualname = class_parts(text, self.home)
        except ClassFormError:
            return []
        if not user_module(module_name):
            reason: str | None = NOT_THE_USER_S
        elif module_name not in sys.modules and module_name not in self.listed:
            reason = NOT_LISTED
        else:
            reason = _step_reason(module_name, qualname)
        if reason is None:
            return []
        if reason in QUOTING:
            return [f"{step_in(place, CLASS_KEY)} {reason} {written(text)}"]
        return [f"{step_in(place, CLASS_KEY)}: {reason}"]


def _step_reason(module_name: str, qualname: str) -> str | None:
    """Why a step of ``qualname``, read in the module with ``plain_attribute``, reaches no class
    of the user's code, or None when each does or the module fails to import."""
    try:
        owner: object = importlib.import_module(module_name)
    except (Exception, SystemExit):
        return None
    parts = qualname.split(".")
    for at, part in enumerate(parts, start=1):
        found = plain_attribute(owner, part)
        if found is Unread.ABSENT:
            return f"{module_name} has no class {qualname}"
        reason = _not_a_user_s_class(found, f"{module_name}::{'.'.join(parts[:at])}")
        if reason is not None:
            return reason
        owner = found
    return None


def _not_a_user_s_class(found: object, reached: str) -> str | None:
    """Why the step that read ``found`` as ``reached`` is not a class of the user's code, or
    None when it is one."""
    if found is Unread.CODE:
        return f"{reached} cannot be read without running code"
    if issubclass(type(found), types.ModuleType):
        return THROUGH_A_MODULE
    if not is_a_class(found):
        return f"{reached} is not a class"
    module = module_of(found)
    return None if isinstance(module, str) and user_module(module) else NOT_THE_USER_S


def _class_names(seed: Mapping[str, object]) -> list[tuple[str, str]]:
    """Each ``"__class__"`` str a seed holds at any depth, with the place of the object that
    holds it, outer before inner in seed order. Read in a loop, not a call per level, so a seed
    as deep as the checks take is read too."""
    found: list[tuple[str, str]] = []
    pending: list[tuple[str, object]] = list(seed.items())[::-1]
    while pending:
        place, item = pending.pop()
        if isinstance(item, dict):
            named = item.get(CLASS_KEY)
            if isinstance(named, str):
                found.append((place, named))
            children = [(step_in(place, key), each) for key, each in item.items()]
        elif isinstance(item, list):
            children = [(step_in(place, at), each) for at, each in enumerate(item)]
        else:
            continue
        pending.extend(reversed(children))
    return found


def _json(seed: Mapping[str, object]) -> str | None:
    """The seed as JSON, or None when it holds a value JSON cannot write, such as an object."""
    try:
        return json.dumps(seed)
    except (TypeError, ValueError):
        return None
