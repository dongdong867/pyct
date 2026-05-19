"""Native `@pre` / `@post` contract primitives + discovery.

This module provides the data shape (``Contract``, ``ContractSet``,
``EMPTY_CONTRACTS``) and the read-only discovery entry point
(``discover_contracts``) that the engine consumes to filter
precondition-violating inputs. The ``pre`` / ``post`` decorators land
in Task 2; for Task 1 the surface is intentionally limited to what the
engine wiring needs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Contract:
    """A single precondition or postcondition discovered on a target.

    Attributes:
        predicate: Callable invoked as ``predicate(**bound)`` where
            ``bound`` is the subset of the engine's concrete args
            named in ``condition_args``. Must return a truthy value
            when the contract holds.
        description: Raw predicate source string, used in violation
            messages. Always populated by the native decorator path.
        source: ``"path:line"`` location captured at decoration time
            via ``inspect.stack()``; surfaced verbatim in violation
            strings emitted by ``_check_preconditions``.
        condition_args: Subset of the target's parameter names that
            the predicate references. Names outside the signature
            (builtins, module globals, ``__return__``) are excluded.
    """

    predicate: Callable[..., Any]
    description: str
    source: str
    condition_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractSet:
    """Aggregated preconditions + postconditions discovered on a target."""

    requires: tuple[Contract, ...] = field(default_factory=tuple)
    ensures: tuple[Contract, ...] = field(default_factory=tuple)


EMPTY_CONTRACTS = ContractSet()


def discover_contracts(target: Any) -> ContractSet:
    """Return the ``ContractSet`` attached to ``target``, or ``EMPTY_CONTRACTS``.

    The native decorators populate ``target.__pyct_contracts__`` at
    decoration time; this reader is a thin ``getattr`` over that
    attribute. Targets without contracts return the singleton
    ``EMPTY_CONTRACTS`` (identity-preserving so callers can use
    ``is`` checks).
    """
    return getattr(target, "__pyct_contracts__", EMPTY_CONTRACTS)


__all__ = [
    "EMPTY_CONTRACTS",
    "Contract",
    "ContractSet",
    "discover_contracts",
]
