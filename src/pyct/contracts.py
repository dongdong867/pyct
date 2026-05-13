"""Read-only discovery of icontract `@require` / `@ensure` decorators."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("ct.contracts")

_LOCATION_RE = re.compile(r"^File (?P<path>.+?), line (?P<line>\d+)")


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
    attached to the wrapped callable. Returns EMPTY_CONTRACTS when the target
    has no contracts.
    """
    requires = _read_preconditions(target)
    ensures = _read_postconditions(target)
    if not requires and not ensures:
        return EMPTY_CONTRACTS
    return ContractSet(requires=requires, ensures=ensures)


def _read_preconditions(target: Any) -> tuple[Contract, ...]:
    groups = getattr(target, "__preconditions__", None) or ()
    return tuple(_to_contract(c) for group in groups for c in group)


def _read_postconditions(target: Any) -> tuple[Contract, ...]:
    items = getattr(target, "__postconditions__", None) or ()
    return tuple(_to_contract(c) for c in items)


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
