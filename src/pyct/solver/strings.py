"""Python strs in SMT-LIB: a literal both ways, an order against a literal, and the searches.

A literal is wrapped in double quotes, and a double quote inside it is
written twice. A printable ASCII character other than the backslash is
written as itself. Every other character up to U+2FFFF, the last one cvc5
holds, is written as ``\\u{hex}`` with its code point in lowercase hex.
cvc5 prints a value by the same rule, so reading one back undoes these
steps. A literal outside double quotes, a piece that is none of the three
forms, or an escape past U+2FFFF is an error.

An order between a string term and a literal is written letter by letter,
the way Python defines string order: the first character that differs
decides, and a string that runs out first is the smaller. cvc5's own
``str.<`` can run to any time limit on a few orders against one-letter
literals that this form answers in milliseconds; decision
string-order-against-a-literal-letter-by-letter.

A search is written as the SMT-LIB term that gives Python's answer, empty
substring included. Each takes its operands already written, the string
first and then the substring.
"""

import re

from pyct.core.strs import LAST_CHARACTER

# the printable ASCII characters, space to tilde: each is written as itself, but for the double
# quote and the backslash
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
    code = _code_point(character)
    if character == '"':
        return '""'
    if _FIRST_PRINTABLE <= code <= _LAST_PRINTABLE and character != "\\":
        return character
    return f"\\u{{{code:x}}}"


def _code_point(character: str) -> int:
    """A character's code point, for one cvc5 holds."""
    code = ord(character)
    if code > LAST_CHARACTER:
        raise ValueError(f"cvc5 holds characters up to U+{LAST_CHARACTER:X}, not U+{code:X}")
    return code


def below(term: str, literal: str, *, or_equal: bool) -> str:
    """``term < literal``, or ``term <= literal`` with ``or_equal``, written letter by letter.

    ``term`` is any String term as SMT-LIB writes it, and ``literal`` the
    Python value. A term that runs out before the literal needs no step of
    its own: ``str.at`` past the end is the empty string, whose code is -1,
    below every character.
    """
    if not literal:
        return f'(= {term} "")' if or_equal else "false"
    steps = [_differs(term, literal, at, "<") for at in range(len(literal))]
    return _any(_equal(term, literal, or_equal) + steps)


def above(term: str, literal: str, *, or_equal: bool) -> str:
    """``literal < term``, or ``literal <= term`` with ``or_equal``, written letter by letter.

    The literal running out first is the last step: the term holds all of
    it and goes on.
    """
    if not literal:
        return "true" if or_equal else f'(distinct {term} "")'
    steps = [_differs(term, literal, at, ">") for at in range(len(literal))]
    longer = f"(and (str.prefixof {encode(literal)} {term}) (> (str.len {term}) {len(literal)}))"
    return _any(_equal(term, literal, or_equal) + steps + [longer])


def _differs(term: str, literal: str, at: int, op: str) -> str:
    """The term agrees with the literal before ``at``, and its letter there is ``op`` of it."""
    letter = f"({op} (str.to_code (str.at {term} {at})) {_code_point(literal[at])})"
    if at == 0:
        return letter
    return f"(and (str.prefixof {encode(literal[:at])} {term}) {letter})"


def _equal(term: str, literal: str, or_equal: bool) -> list[str]:
    """The equality an ``or_equal`` order also takes, or nothing for a strict one."""
    return [f"(= {term} {encode(literal)})"] if or_equal else []


def _any(parts: list[str]) -> str:
    """Any of the parts holds. One part is itself."""
    return parts[0] if len(parts) == 1 else f"(or {' '.join(parts)})"


def first_index(term: str, sub: str) -> str:
    """``s.find(sub)``: where sub first starts in s, or -1.

    cvc5's ``str.indexof`` from 0 is Python's answer as it stands, the empty
    substring found at 0 included.
    """
    return f"(str.indexof {term} {sub} 0)"


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
