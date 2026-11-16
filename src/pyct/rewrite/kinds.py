"""Which of an input's arguments a rewrite may read: each parameter is an object, holds one, or is
plain, on that input.

A parameter is an object when the input builds it: from a seed's object form,
from a dict or list under a class hint (``seed_form``), or as the instance a
method runs on, from the dict under its ``self`` parameter. A value of any type
but exactly None, bool, int, float, str, list, tuple and dict, as an instance a
``run()`` caller hands in, is an object too. A parameter holds an object when
its lists, tuples and dicts hold one at any depth, each item of a list and each
value of a dict read under what its hint asks of its items (``item_check``), so
a list under ``list[Order]`` holds one. Every other parameter is plain, and a
rewrite reads plain parameters alone (decision
llm-a-rewrite-reads-no-parameter-that-holds-an-object).

The hints are the ones each input's ``Seed.checks`` holds, read as the input's
own build reads them. Each type is compared with the plain ones by identity, so
no hook of a value's class or metaclass runs in pyct's process to tell them
apart.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from pyct.binding.annotations import Check, item_check
from pyct.binding.bind import Seed
from pyct.binding.builds import seed_form

# the plain types a value a rewrite may read can have, each compared by identity
_SCALARS: tuple[type, ...] = (type(None), bool, int, float, str)


class Kind(enum.Enum):
    """What a parameter is on one input."""

    PLAIN = "plain"
    OBJECT = "an object"
    HOLDS_OBJECT = "holds an object"


@dataclass(frozen=True)
class Kinds:
    """What tells an input's objects apart: what each parameter's hint asks, and the parameter
    whose dict each input builds the instance a method runs on from, None for any other
    target."""

    checks: Mapping[str, Check] = field(default_factory=dict)
    self_name: str | None = None

    @classmethod
    def of_seed(cls, seed: Seed, self_name: str | None = None) -> Kinds:
        """The kinds under the hints ``seed`` was made with."""
        return cls(seed.checks, self_name)

    def of(self, name: str, value: object) -> Kind:
        """The kind of parameter ``name``, holding ``value``. The method's ``self`` is built only
        from exactly a dict, as each input builds it."""
        if name == self.self_name and type(value) is dict:
            return Kind.OBJECT
        return kind_of(value, self.checks.get(name))

    def plain(self, args: Mapping[str, object], names: Sequence[str]) -> bool:
        """Whether ``args`` holds each name, each plain."""
        return all(name in args and self.of(name, args[name]) is Kind.PLAIN for name in names)


def kind_of(value: object, check: Check | None = None) -> Kind:
    """The kind of ``value``, under the hint ``check`` at its place. Read in a loop, each list,
    tuple and dict once."""
    if _an_object(value, check):
        return Kind.OBJECT
    pending = _held(value, check)
    seen = {id(value)}
    while pending:
        each, asks = pending.pop()
        if _an_object(each, asks):
            return Kind.HOLDS_OBJECT
        if id(each) not in seen:
            seen.add(id(each))
            pending.extend(_held(each, asks))
    return Kind.PLAIN


def _an_object(value: object, check: Check | None) -> bool:
    """Whether the input builds ``value`` as an object, under ``check``, or ``value`` is of a
    type other than the plain ones and exactly list, tuple and dict."""
    kind = type(value)
    if any(kind is scalar for scalar in _SCALARS) or kind is tuple:
        return False
    if kind is list or kind is dict:
        return seed_form(value, check)
    return True


def _held(holder: object, check: Check | None) -> list[tuple[object, Check | None]]:
    """A list's or tuple's items, or a dict's keys and values, each with what ``check`` asks of
    it; none for any other value."""
    kind = type(holder)
    if kind is list:
        items = cast(list[object], holder)
        return [(item, item_check(check, list, at)) for at, item in enumerate(items)]
    if kind is tuple:
        return [(item, None) for item in cast(tuple[object, ...], holder)]
    if kind is dict:
        pairs = cast(dict[object, object], holder)
        keys = [(key, None) for key in pairs]
        return [*keys, *((item, item_check(check, dict, key)) for key, item in pairs.items())]
    return []
