"""A sweep fixture: a package that re-exports classes written outside it."""

from ..core import Gadget, Meter, Widget

__all__ = ["Gadget", "Meter", "Widget", "gauge"]


def gauge(n: int) -> int:
    return n
