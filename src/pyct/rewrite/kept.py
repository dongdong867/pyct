"""Kept rewrites: each condition's rewrite whose input took the wanted side, reused in every later
ask that holds that condition at that side, until one of its inputs takes the other side.

Each use runs the rewrite again, in a child of pyct's process, on the
input whose path that ask extends, since the forks it records depend on
that input. A condition whose rewrite does not run, or records nothing to
put in its place, keeps its own fork in that ask.
"""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.core.foundation.branch import Branch, Fact
from pyct.results.causes import Condition
from pyct.results.record import InputRecord
from pyct.rewrite.ask import RunRewrite, holding, in_place, recorded, takes
from pyct.rewrite.condition import holds_object


@dataclass(frozen=True)
class Reused:
    """A plan's ask with the kept rewrites in place of their conditions, and those conditions."""

    asked: tuple[Branch | Fact, ...]
    conditions: tuple[Condition, ...]


class Kept:
    """The rewrite kept for each condition: its code, and the names it may read."""

    def __init__(self) -> None:
        self.codes: dict[Condition, tuple[types.CodeType, tuple[str, ...]]] = {}

    def keep(self, condition: Condition, code: types.CodeType, parameters: tuple[str, ...]) -> None:
        self.codes[condition] = (code, parameters)

    def reused(self, plan: Plan, origin: Seed, run: RunRewrite) -> Reused | None:
        """The plan's ask with each kept rewrite the plan holds in its condition's place, each
        run on ``origin``; None when no kept rewrite takes a place in it. A rewrite reading a
        name the input does not hold, or one that holds an object there, takes none."""
        asked = plan.asked
        used: list[Condition] = []
        for condition, (code, parameters) in self.codes.items():
            if not holding(plan, condition) or not _readable(origin.args, parameters):
                continue
            ran = run(code, {name: origin.args[name] for name in parameters})
            items = None if isinstance(ran, str) else recorded(ran, code.co_filename)
            if items is None or isinstance(items, str):
                continue
            asked = in_place(asked, condition, items.items)
            used.append(condition)
        return Reused(asked, tuple(used)) if used else None

    def judged(self, record: InputRecord, conditions: Sequence[Condition]) -> tuple[Condition, ...]:
        """Drop the rewrite of each condition the input, whose ask used it, did not take the
        wanted side of, and name those conditions."""
        dropped = tuple(each for each in conditions if not takes(record, each))
        for condition in dropped:
            self.codes.pop(condition, None)
        return dropped


def _readable(args: Mapping[str, object], names: Sequence[str]) -> bool:
    """Whether ``args`` holds each name, and none holds an object there (``holds_object``)."""
    return all(name in args and not holds_object(args[name]) for name in names)
