"""What the solver reads of a tracked str's plain operands: a literal, a position, a flag."""

from __future__ import annotations

# the last character cvc5 holds: its strings run from U+0000 to here, and the solver writes
# every one of them
LAST_CHARACTER = 0x2FFFF


def within_cvc5(text: str) -> bool:
    """Whether the solver holds every character of a plain str as it is."""
    return all(ord(character) <= LAST_CHARACTER for character in text)


def position(value: object) -> int | None:
    """A position pyct encodes, a plain int or a plain bool, as the int it indexes with.

    Any other value is None.
    """
    return int(value) if isinstance(value, int) and type(value) in (int, bool) else None
