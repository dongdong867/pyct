"""Where a target elsewhere gets an ``__init__``, a ``__new__`` or a ``__call__``.

A base gives the first three; a metaclass gives the ``__call__``
``inspect.signature`` reads a class through when it has one.

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

    def __new__(cls, n: str, m: int) -> "MakingBase":
        return super().__new__(cls)


class AgreeingMakingBase:
    """A base whose ``__new__`` text only this module can resolve."""

    def __new__(cls, n: str) -> "AgreeingMakingBase":
        return super().__new__(cls)


class CallingBase:
    """A base whose ``__call__``, and its text, a callable object takes."""

    def __call__(self, n: str, m: int) -> None:
        return None


class AgreeingCallingBase:
    """A base whose ``__call__`` text only this module can resolve."""

    def __call__(self, n: str) -> None:
        return None


class Meta(type):
    """A metaclass whose ``__call__``, and its text, a class elsewhere is read through."""

    def __call__(cls, n: str, m: int) -> object:
        return super().__call__()


class AgreeingMeta(type):
    """A metaclass whose ``__call__`` text only this module can resolve."""

    def __call__(cls, n: str) -> object:
        return super().__call__()


# what ``from __future__ import annotations`` leaves behind on each dunder
Base.__init__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
AgreeingBase.__init__.__annotations__ = {"n": "Elsewhere", "return": "None"}
MakingBase.__new__.__annotations__ = {"n": "Number", "m": "int", "return": "MakingBase"}
AgreeingMakingBase.__new__.__annotations__ = {"n": "Elsewhere", "return": "AgreeingMakingBase"}
CallingBase.__call__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
AgreeingCallingBase.__call__.__annotations__ = {"n": "Elsewhere", "return": "None"}
Meta.__call__.__annotations__ = {"n": "Number", "m": "int", "return": "object"}
AgreeingMeta.__call__.__annotations__ = {"n": "Elsewhere", "return": "object"}
