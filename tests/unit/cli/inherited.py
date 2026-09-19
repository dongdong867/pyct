"""Bases whose ``__init__``, ``__new__`` or ``__call__`` a target elsewhere takes.

``Number`` is a ``str`` here and an ``int`` in ``test_checks``, so a text
annotation written here means a different plain type depending on which
module's names read it. ``Elsewhere`` is spelled only here, so it is a name
this module knows and ``test_checks`` does not.
"""

# the name both modules spell, each meaning a different plain type
Number = str
# the name only this module spells
Elsewhere = str


class Base:
    """The class an inheriting target gets its ``__init__``, and its text, from."""

    def __init__(self, n: str, m: int) -> None:
        self.value = n


class AgreeingBase:
    """A base whose ``__init__`` text only this module can resolve."""

    def __init__(self, n: str) -> None:
        self.value = n


class MakingBase:
    """A base whose ``__new__``, and its text, an inheriting target takes."""

    def __new__(cls, n: str) -> "MakingBase":
        return super().__new__(cls)


class CallingBase:
    """A base whose ``__call__``, and its text, a callable object takes."""

    def __call__(self, n: str, m: int) -> None:
        return None


class AgreeingCallingBase:
    """A base whose ``__call__`` text only this module can resolve."""

    def __call__(self, n: str) -> None:
        return None


# what ``from __future__ import annotations`` leaves behind on each dunder
Base.__init__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
AgreeingBase.__init__.__annotations__ = {"n": "Elsewhere", "return": "None"}
MakingBase.__new__.__annotations__ = {"n": "Number", "return": "MakingBase"}
CallingBase.__call__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
AgreeingCallingBase.__call__.__annotations__ = {"n": "Elsewhere", "return": "None"}
