"""A constructor whose annotations are text that only this module's names resolve.

``Counts`` is spelled here alone, so the module of a method on a class that inherits this
constructor cannot read the annotation; the constructor's own module can.
"""

from __future__ import annotations

# the name only this module spells
Counts = dict[int, int]


class Base:
    def __init__(self, owner: str, /, counts: Counts) -> None:
        self.owner = owner
        self.counts = counts
