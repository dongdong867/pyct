"""What the solver reads of a tracked str's plain operands: a literal, a position, a flag."""

from __future__ import annotations

# the last character cvc5 holds: its strings run from U+0000 to here, and the solver writes
# every one of them
LAST_CHARACTER = 0x2FFFF


def within_cvc5(text: str) -> bool:
    """Whether the solver holds every character of a plain str as it is."""
    return all(ord(character) <= LAST_CHARACTER for character in text)


def literal(value: object, tracked: type) -> str | None:
    """A plain str the solver reads as it is, written as repr writes it, or None.

    ``tracked`` is the tracked str's own type: a value of it is not plain,
    and neither is a non-str or a str holding a character past the last one
    cvc5 holds. str's own repr, since a str of the target's own may print
    itself another way.
    """
    if not isinstance(value, str) or isinstance(value, tracked) or not within_cvc5(value):
        return None
    return str.__repr__(value)


def plain(value: object) -> str:
    """A str's own text as a plain str, read without any method of a subclass of the target's."""
    if not isinstance(value, str):
        raise TypeError(f"pyct reads the text of a str, not of {type(value).__name__}")
    return str.__str__(value)


def position(value: object) -> int | None:
    """A position pyct encodes, a plain int or a plain bool, as the int it indexes with.

    Any other value is None.
    """
    return int(value) if isinstance(value, int) and type(value) in (int, bool) else None
