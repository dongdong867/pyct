"""A base class whose ``__init__`` an inheriting class in another module takes.

``Number`` is a ``str`` here and an ``int`` in ``test_checks``, so the text
annotation on ``__init__`` resolves to a different plain type depending on
which module's names read it.
"""

# the name the base's text annotation is written against, spelled only here
Number = str


class Base:
    """The class an inheriting target gets its ``__init__``, and its text, from."""

    def __init__(self, n: str) -> None:
        self.value = n


# what ``from __future__ import annotations`` leaves behind on the base's __init__
Base.__init__.__annotations__ = {"n": "Number", "return": "None"}
