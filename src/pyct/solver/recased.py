"""``title`` and ``swapcase`` in SMT-LIB: each letter's case chosen by what is around it.

``swapcase`` turns each letter the other case, and ``title`` makes a letter
uppercase after a character that is not a letter and lowercase after one
that is. No SMT-LIB operation maps a string letter by letter, so the first
`HEAD` characters are each written out, a character past the end being the
empty string, and the rest of the string is a string of its own, declared
and held to the conditions that make it Python's answer. cvc5 answers a
string of up to `HEAD` characters at once either way, and one longer than
that as it can, where the declared rest alone ran eight letters past a ten
second limit. Exact for ASCII; a letter past ASCII has no case, as in
`checks`.
"""

from collections.abc import Callable, Mapping

from pyct.solver.checks import LOWER, NOT_LETTER, TITLE_CASED, UPPER, one_of
from pyct.solver.strings import length

# how many characters are written out one by one, before the declared rest. More makes cvc5
# slower at a short string asked of the result, measured at 16
HEAD = 8

# the code points of the ASCII letters, each case from its first to its last, as the checks
# class them
(_UPPER_CODES,) = UPPER
(_LOWER_CODES,) = LOWER
_CASE_SHIFT = _LOWER_CODES[0] - _UPPER_CODES[0]

# a value with a declared name in it: the name's sort, the value's term, and the condition
# that holds it to Python's answer
type Declared = tuple[str, str, str]


def _within(code: str, codes: tuple[int, int]) -> str:
    """The code is in the run of codes."""
    first, last = codes
    return f"(and (<= {first} {code}) (<= {code} {last}))"


def _letter(code: str) -> str:
    """The code is an ASCII letter's."""
    return f"(or {_within(code, _UPPER_CODES)} {_within(code, _LOWER_CODES)})"


def _code(term: str, at: int) -> str:
    """The code of the term's character at ``at``, -1 past its end."""
    return f"(str.to_code (str.at {term} {at}))"


def _raised(code: str) -> str:
    """The code uppercase: a lowercase letter's shifted, any other as it is."""
    return f"(ite {_within(code, _LOWER_CODES)} (- {code} {_CASE_SHIFT}) {code})"


def _lowered(code: str) -> str:
    """The code lowercase: an uppercase letter's shifted, any other as it is."""
    return f"(ite {_within(code, _UPPER_CODES)} (+ {code} {_CASE_SHIFT}) {code})"


def _swapped_at(term: str, at: int) -> str:
    """The character at ``at`` the other case, or empty past the end."""
    flipped = f"(ite {_within('c!', _LOWER_CODES)} (- c! {_CASE_SHIFT}) {_lowered('c!')})"
    return f"(let ((c! {_code(term, at)})) (str.from_code {flipped}))"


def _titled_at(term: str, at: int) -> str:
    """The character at ``at`` as title makes it, or empty past the end."""
    if at == 0:
        cased = _raised("c!")
    else:
        cased = f"(ite {_letter(_code(term, at - 1))} {_lowered('c!')} {_raised('c!')})"
    return f"(let ((c! {_code(term, at)})) (str.from_code {cased}))"


def _head(term: str, at: Callable[[str, int], str]) -> str:
    """The term's first `HEAD` characters, each as ``at`` writes it."""
    return f"(str.++ {' '.join(at(term, index) for index in range(HEAD))})"


def _rest(term: str) -> str:
    """The term past its first `HEAD` characters, empty for a shorter one."""
    return f"(str.substr {term} {HEAD} (- {length(term)} {HEAD}))"


def _cased_alike(name: str, term: str) -> str:
    """The two strings are one string, but for the case of their letters."""
    return f"(= (str.to_lower {name}) (str.to_lower {term}))"


def swapped(name: str, term: str) -> Declared:
    """``s.swapcase()``: its head written out, then ``name``, held to be the rest swapped.

    ``name`` and the rest are one string uppercased. Each lowercase letter
    of ``name`` and each uppercase letter of the rest is marked with U+0000,
    and the rest's marked string is uppercased; the two are then one string,
    so ``name``'s letter is lowercase just where the rest's is uppercase, and
    uppercase just where the rest's is lowercase. A U+0000 of s's own stays
    itself on both sides.
    """
    rest = _rest(term)
    marked = f'(str.replace_re_all {name} {one_of(LOWER)} "\\u{{0}}")'
    was = f'(str.to_upper (str.replace_re_all {rest} {one_of(UPPER)} "\\u{{0}}"))'
    condition = f"(and (= (str.to_upper {name}) (str.to_upper {rest})) (= {marked} {was}))"
    return "String", f"(str.++ {_head(term, _swapped_at)} {name})", condition


def titled(name: str, term: str) -> Declared:
    """``s.title()``: its head written out, then ``name``, held to be the rest as title makes it.

    The rest is title case with the letters of the rest, and when the head
    ends in a letter, a run of lowercase letters comes first.
    """
    rest = _rest(term)
    after_letter = _letter(_code(term, HEAD - 1))
    continued = f"(re.++ (re.* {one_of(LOWER)}) (re.opt (re.++ {NOT_LETTER} {TITLE_CASED})))"
    cased = f"(ite {after_letter} (str.in_re {name} {continued}) (str.in_re {name} {TITLE_CASED}))"
    condition = f"(and {_cased_alike(name, rest)} {cased})"
    return "String", f"(str.++ {_head(term, _titled_at)} {name})", condition


# a str no term writes whole: each takes a declared name and the string rendered, and gives
# the name's sort, the value's term and the condition that makes it Python's answer
TO_DECLARE: Mapping[str, Callable[[str, str], Declared]] = {"title": titled, "swapcase": swapped}
