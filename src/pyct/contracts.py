"""Read-only discovery of icontract `@require` / `@ensure` decorators."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("ct.contracts")


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

    Returns EMPTY_CONTRACTS until extraction lanes land.
    """
    del target
    return EMPTY_CONTRACTS
