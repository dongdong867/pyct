"""Turn a seed dict into the arguments the target is called with."""

from collections.abc import Mapping

from pyct.core.branch import BranchSink
from pyct.core.values import ConcolicInt


def bind(seed: Mapping[str, object], sink: BranchSink) -> dict[str, object]:
    """Give every int in the seed its parameter's name and the sink.

    A bool is an int to Python but not a number to bind: it has no ``<``
    worth tracking. Every other value passes through as it came.
    """
    return {name: _bound(name, value, sink) for name, value in seed.items()}


def _bound(name: str, value: object, sink: BranchSink) -> object:
    if isinstance(value, int) and not isinstance(value, bool):
        return ConcolicInt(value, expression=name, sink=sink)
    return value
