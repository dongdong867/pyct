"""A sweep fixture: a package that re-exports a bound method one of its modules exposes."""

from .core import roll

__all__ = ["roll"]
