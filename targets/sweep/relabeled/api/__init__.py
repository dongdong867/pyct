"""A sweep fixture: a package that re-exports a class written outside it."""

from ..core import Widget

__all__ = ["Widget", "gauge"]


def gauge(n: int) -> int:
    return n
