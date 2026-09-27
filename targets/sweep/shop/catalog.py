"""A sweep fixture: a module that exports a function another module defines."""

from .prices import total

__all__ = ["total"]
