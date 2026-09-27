"""A sweep fixture: a package that re-exports a bound method one of its modules exposes, whose
code is in a third module that does not expose it."""

from .api import parse

__all__ = ["parse"]
