"""A base class whose annotations are kept as text, naming types only this module binds."""

from __future__ import annotations

Count = int
Name = str


class Base:
    def __init__(self, owner: Name):
        self.owner = owner

    def describe(self, level: Count):
        if level > 3:
            return self.owner
        return ""
