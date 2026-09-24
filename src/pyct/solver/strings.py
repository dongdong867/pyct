"""A Python str as an SMT-LIB string literal, and a literal cvc5 prints as a str again.

A literal is wrapped in double quotes, and a double quote inside it is
written twice. A printable ASCII character other than the backslash is
written as itself. Every other character up to U+2FFFF, the last one cvc5
holds, is written as ``\\u{hex}`` with its code point in lowercase hex.
cvc5 prints a value by the same rule, so reading one back undoes exactly
these steps; a literal that breaks the rule is an error.
"""

import re

from pyct.core.strs import LAST_CHARACTER

# the printable ASCII characters, space to tilde: each is written as itself but these two
_FIRST_PRINTABLE = 0x20
_LAST_PRINTABLE = 0x7E

# one piece of a literal as cvc5 prints it: a doubled quote, an escape, or a printable ASCII
# character that is neither the quote nor the backslash
_PIECE = re.compile(r'(?P<quote>"")|\\u\{(?P<code>[0-9a-f]{1,5})\}|(?P<plain>[ !#-\[\]-~])')


def encode(value: str) -> str:
    """The SMT-LIB literal cvc5 reads as ``value``."""
    return '"' + "".join(_encoded(character) for character in value) + '"'


def _encoded(character: str) -> str:
    """One character as it sits inside a literal."""
    code = ord(character)
    if character == '"':
        return '""'
    if _FIRST_PRINTABLE <= code <= _LAST_PRINTABLE and character != "\\":
        return character
    if code > LAST_CHARACTER:
        raise ValueError(f"cvc5 holds characters up to U+{LAST_CHARACTER:X}, not U+{code:X}")
    return f"\\u{{{code:x}}}"


def decode(literal: str) -> str:
    """The str a literal cvc5 printed stands for."""
    if len(literal) < 2 or literal[0] != '"' or literal[-1] != '"':
        raise ValueError(f"cvc5 prints a string value in double quotes, not {literal}")
    body = literal[1:-1]
    pieces: list[str] = []
    at = 0
    while at < len(body):
        piece = _PIECE.match(body, at)
        if piece is None:
            raise ValueError(f"cvc5 prints no string value like {literal}")
        pieces.append(_decoded(piece, literal))
        at = piece.end()
    return "".join(pieces)


def _decoded(piece: re.Match[str], literal: str) -> str:
    """One piece of a literal as the character it stands for."""
    if piece["quote"] is not None:
        return '"'
    if piece["plain"] is not None:
        return piece["plain"]
    code = int(piece["code"], 16)
    if code > LAST_CHARACTER:
        raise ValueError(f"cvc5 holds characters up to U+{LAST_CHARACTER:X}: {literal}")
    return chr(code)
