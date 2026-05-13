"""Read-only discovery of icontract `@require` / `@ensure` decorators."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("ct.contracts")

_LOCATION_RE = re.compile(r"^File (?P<path>.+?), line (?P<line>\d+)")
_MAX_WRAPPED_DEPTH = 10


@dataclass(frozen=True)
class Contract:
    predicate: Callable[..., bool]
    description: str | None
    source: str


@dataclass(frozen=True)
class ContractSet:
    requires: tuple[Contract, ...] = ()
    ensures: tuple[Contract, ...] = ()


EMPTY_CONTRACTS = ContractSet()


def discover_contracts(target: Any) -> ContractSet:
    """Discover icontract preconditions/postconditions on `target`.

    Reads icontract's `__preconditions__` and `__postconditions__` attributes
    attached to the wrapped callable. Walks `__wrapped__` when the direct read
    is empty, with cycle detection and a depth cap. Returns EMPTY_CONTRACTS
    when no contracts surface.
    """
    visited: set[int] = set()
    current: Any = target
    for _ in range(_MAX_WRAPPED_DEPTH + 1):
        if id(current) in visited:
            return EMPTY_CONTRACTS
        visited.add(id(current))
        requires = _read_preconditions(current)
        ensures = _read_postconditions(current)
        if requires or ensures:
            return ContractSet(requires=requires, ensures=ensures)
        wrapped = getattr(current, "__wrapped__", None)
        if wrapped is None or wrapped is current:
            return EMPTY_CONTRACTS
        current = wrapped
    return EMPTY_CONTRACTS


def _read_preconditions(target: Any) -> tuple[Contract, ...]:
    groups = getattr(target, "__preconditions__", None) or ()
    # icontract stores innermost-first; reverse to recover source order.
    return tuple(_to_contract(c) for group in groups for c in reversed(group))


def _read_postconditions(target: Any) -> tuple[Contract, ...]:
    items = getattr(target, "__postconditions__", None) or ()
    return tuple(_to_contract(c) for c in reversed(items))


def _to_contract(raw: Any) -> Contract:
    return Contract(
        predicate=raw.condition,
        description=raw.description,
        source=_parse_location(raw.location),
    )


def _parse_location(location: str) -> str:
    match = _LOCATION_RE.match(location)
    if not match:
        return location
    return f"{match['path']}:{match['line']}"
