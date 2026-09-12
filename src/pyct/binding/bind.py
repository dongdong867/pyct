"""Turn a seed dict into the arguments the target is called with."""

from collections.abc import Mapping
from typing import TypeGuard

from pyct.core.branch import BranchSink
from pyct.core.values import ConcolicInt


def bind(seed: Mapping[str, object], sink: BranchSink) -> dict[str, object]:
    """Give every int in the seed its parameter's name and the sink.

    A bool is an int to Python but not a number to bind: it has no ``<``
    worth tracking. Every other value passes through as it came.
    """
    return {name: _bound(name, value, sink) for name, value in seed.items()}


def leaves(seed: Mapping[str, object]) -> Mapping[str, type]:
    """The name and type of every argument ``bind`` wraps, in the seed's order.

    This is what the solver is allowed to answer about: nothing else in the
    seed carries a condition back.
    """
    return {name: type(value) for name, value in seed.items() if _binds(value)}


def _binds(value: object) -> TypeGuard[int]:
    """Whether bind wraps this value: the one rule both sides read."""
    return isinstance(value, int) and not isinstance(value, bool)


def _bound(name: str, value: object, sink: BranchSink) -> object:
    if _binds(value):
        return ConcolicInt(value, expression=name, sink=sink)
    return value
