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
substring included. Each takes its operands already written, in the order
the expression holds them: the string and then the substring, but for
``in``, whose needle comes first. SMT-LIB has no last index and no count,
so ``rfind`` and ``count`` read the reversed strings, and each term also
states a bound Python's answer always meets, which cvc5 does not work out
from the rest; decision string-search-clamped-over-the-reversed-string.
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


def contains(sub: str, term: str) -> str:
    """``sub in s``, taking its operands in Python's order, the needle first.

    cvc5's ``str.contains`` takes them the other way round. The empty
    substring is in every string in both.
    """
    return f"(str.contains {term} {sub})"


def first_index(term: str, sub: str) -> str:
    """``s.find(sub)``: where sub first starts in s, or -1.

    cvc5's ``str.indexof`` from 0 is Python's answer as it stands, the empty
    substring found at 0 included.
    """
    return f"(str.indexof {term} {sub} 0)"


def starts_with(term: str, prefix: str) -> str:
    """``s.startswith(prefix)``: cvc5's ``str.prefixof``, which takes the prefix first."""
    return f"(str.prefixof {prefix} {term})"


def ends_with(term: str, suffix: str) -> str:
    """``s.endswith(suffix)``: cvc5's ``str.suffixof``, which takes the suffix first."""
    return f"(str.suffixof {suffix} {term})"


def last_index(term: str, sub: str) -> str:
    """``s.rfind(sub)``: where sub last starts in s, or -1.

    It is where the reversed sub first starts in the reversed s, counted
    back from the end, so the empty substring is found at ``len(s)``, as
    Python finds it. The answer is held at or above the first index, where
    it always is: without that bound cvc5 ran paths holding both to its time
    limit.
    """
    first = first_index(term, sub)
    reversed_first = f"(str.indexof {_reversed(term)} {_reversed(sub)} 0)"
    back = f"(- (- {_length(term)} {_length(sub)}) {reversed_first})"
    return f"(ite (str.contains {term} {sub}) (ite (< {back} {first}) {first} {back}) (- 1))"


def occurrences(term: str, sub: str) -> str:
    """``s.count(sub)``: how many times sub occurs in s without overlapping.

    Every sub removed, what went divided by sub's length is the count. The
    removal runs on the reversed strings, as `last_index` reads them: a
    greedy count from either end finds as many, and cvc5 ran paths mixing a
    count on the plain strings with a last index to its time limit. The
    count is held at one or more where sub is in s and is 0 where it is not,
    which cvc5 does not work out from the removal. The empty substring
    occurs ``len(s) + 1`` times, as Python counts it.
    """
    removed = f'(str.replace_all {_reversed(term)} {_reversed(sub)} "")'
    counted = f"(div (- {_length(term)} (str.len {removed})) {_length(sub)})"
    return (
        f'(ite (= {sub} "") (+ {_length(term)} 1)'
        f" (ite (str.contains {term} {sub}) (ite (< {counted} 1) 1 {counted}) 0))"
    )


def _reversed(term: str) -> str:
    """A string term reversed.

    A literal is reversed here and written as the literal it becomes:
    cvc5 answered some paths with that literal at once and ran them to its
    time limit with the same literal under ``str.rev``.
    """
    if _is_literal(term):
        return encode(decode(term)[::-1])
    return f"(str.rev {term})"


def _length(term: str) -> str:
    """A string term's length. A literal's is counted here, as its reversal is."""
    return str(len(decode(term))) if _is_literal(term) else f"(str.len {term})"


def _is_literal(term: str) -> bool:
    """Whether a written term is a literal: a name never opens with a quote, a term with `(`."""
    return term.startswith('"')


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
