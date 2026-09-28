"""A number written as text, read as Python's `int` and `float` read it, and written as `str`
writes it.

``isint`` and ``isfloat`` hold for a string Python's own `int(s)` and
`float(s)` accept, and ``int`` and ``float`` of a string are the number it
reads. Each is exact for ASCII: Python's grammar is written as a regular
expression, with the six ASCII characters both strip around the number, an
optional sign, and single underscores between digits. Past ASCII Python also
reads the digits and the spaces of other scripts, which these read as text
that is no number, so an input the solver hands back may leave the plan
there (``README.md › Rules › string encodings``).

`int` reads at most `sys.get_int_max_str_digits()` digits, as Python does
when pyct runs, underscores left out; a string with more raises ValueError.
One character of a string, as `s[i]` hands it out, is read by forms of its
own: of the ASCII characters Python reads only the ten digits there, as the
digit it is, so its forms need no grammar, no count and no pass over the
text, which cost cvc5 seconds for each character a loop reads (decision
int-text-digits-in-one-pass-and-a-character-as-a-digit).

`float` of a string is exact inside a bound, which the path holds on a first
ask (see ``Program.bounded`` in ``solver/render.py``): a string of digits
with an optional minus, an optional point and fraction, and no exponent,
underscore or space, whose digits make at most 2**53 when it has a fraction
of at most 22 digits, and ``nan``, ``inf`` and ``-inf``. A whole number is
one correct rounding of an Int, and a fraction one correct division of such
an Int by a power of ten a double holds exactly, which is Python's double
to the last bit. Past the bound the term is a double of its own, so an
unsat there holds for every value Python reads, and a sat is ``unknown``.

``str`` of an int is its decimal digits, with ``-`` before a negative one,
and ``str`` of a bool is ``True`` or ``False``, each exact.

A form here names the parts it reads more than once with ``let``, as
``b!``, ``d!``, ``i!``, ``f!``, ``k!``, ``a!``, ``n!`` and ``g!``,
which no name render writes can be (see ``solver/floats.py``).
"""

import math
import sys

from pyct.solver.floats import literal

# the characters Python's `int` and `float` strip around a number, as ASCII
_SPACES = " \t\n\x0b\x0c\r"

# how many powers of ten a double holds exactly, 10**0 to 10**22
_EXACT_POWERS = 22

# the largest whole number every smaller one of which a double holds exactly
_EXACT_WHOLE = 2**53

# the most digits `int_fact` names a power of ten for
_COUNTED_DIGITS = 20


def _characters(characters: str) -> str:
    """A regular expression for any one of the characters."""
    each = " ".join(f'(str.to_re "\\u{{{ord(character):x}}}")' for character in characters)
    return f"(re.union {each})"


_SPACE = _characters(_SPACES)
_DIGIT = '(re.range "0" "9")'
# digits, with single underscores between them
_DIGITS = f'(re.++ {_DIGIT} (re.* (re.++ (re.opt (str.to_re "_")) {_DIGIT})))'
_SIGN = f"(re.opt {_characters('+-')})"
# digits alone, as `s.isdigit()` holds them for ASCII (see ``solver/checks.py``)
_PLAIN_DIGITS = f"(re.+ {_DIGIT})"
# every character other than a digit Python's `int` reads in a number
_NOT_DIGITS = _characters(_SPACES + "_+-")


def _digits(term: str) -> str:
    """The digits of an int Python reads, without its spaces, underscores and sign.

    One pass takes out every such character: the same string a pass for each kind leaves,
    which cvc5 answers faster (decision int-text-digits-in-one-pass-and-a-character-as-a-digit).
    """
    return f'(str.replace_re_all {term} {_NOT_DIGITS} "")'


def is_int(term: str) -> str:
    """Python's `int(s)` accepts the string: spaces, a sign, and digits with underscores.

    The grammar names a string of plain digits on its own as well, the same language: cvc5
    then sees at once that a string `s.isdigit()` holds for is one it accepts, where the
    grammar alone took it seconds, or past any limit with no bound on the string's length.
    """
    written = f"(re.++ (re.* {_SPACE}) {_SIGN} {_DIGITS} (re.* {_SPACE}))"
    grammar = f"(re.union {_PLAIN_DIGITS} {written})"
    matched = f"(str.in_re {term} {grammar})"
    most = sys.get_int_max_str_digits()
    if most == 0:
        return matched
    return f"(and {matched} (<= (str.len {_digits(term)}) {most}))"


def int_of(term: str) -> str:
    """The int Python's `int(s)` reads, where it accepts the string.

    A minus can only be the sign there, so its presence says the number is
    negative. The digits there are one or more, so their Int is never
    negative, and ``abs`` changes nothing; it says so to cvc5, which does not
    tie `str.to_int`'s -1 for text that is no number to the grammar, and ran
    past its limit asking whether a digit string reads as a negative int.
    """
    magnitude = f"(abs (str.to_int {_digits(term)}))"
    return f'(ite (str.contains {term} "-") (- {magnitude}) {magnitude})'


def int_fact(term: str) -> str:
    """A fact about the int `int_of` reads, true of every string: its digits' Int is below ten
    to the power of their count, for each count up to ``_COUNTED_DIGITS``.

    cvc5 does not tie `str.to_int` to the length of its string, and took seconds to see that no
    string of five digits reads as 100000; with this fact it answers at once. Text that is no
    number reads as -1 there, and so meets it too.
    """
    number = "(str.to_int d!)"
    each = " ".join(
        f"(=> (<= (str.len d!) {count}) (< {number} {10**count}))"
        for count in range(1, _COUNTED_DIGITS + 1)
    )
    return f"(let ((d! {_digits(term)})) (and {each}))"


def is_int_character(term: str) -> str:
    """Python's `int(c)` accepts one character: it is a digit."""
    return f"(str.in_re {term} {_DIGIT})"


def int_of_character(term: str) -> str:
    """The int Python's `int(c)` reads from one character it accepts: the digit's value."""
    return f"(str.to_int {term})"


def text_of_int(term: str) -> str:
    """The text Python's `str(n)` writes for an int: its decimal digits, `-` before a negative.

    `str.from_int` writes a natural number's digits, the reverse of what
    `int_of` reads, so a negative one is written by its magnitude after the
    sign. Python's limit on the digits it writes is not held here.
    """
    return f'(ite (< {term} 0) (str.++ "-" (str.from_int (- {term}))) (str.from_int {term}))'


def text_of_bool(term: str) -> str:
    """The text Python's `str(b)` writes for a bool: `True` or `False`."""
    return f'(ite {term} "True" "False")'


def _letters(word: str) -> str:
    """A regular expression for the word in any case."""
    each = " ".join(_characters(letter + letter.upper()) for letter in word)
    return f"(re.++ {each})"


_NUMBER = (
    f'(re.union (re.++ {_DIGITS} (re.opt (re.++ (str.to_re ".") (re.opt {_DIGITS}))))'
    f' (re.++ (str.to_re ".") {_DIGITS}))'
)
_EXPONENT = f"(re.++ {_characters('eE')} {_SIGN} {_DIGITS})"
_SPECIAL = f"(re.union (re.++ {_letters('inf')} (re.opt {_letters('inity')})) {_letters('nan')})"


def is_float(term: str) -> str:
    """Python's `float(s)` accepts the string: a decimal with an exponent, an infinity or NaN."""
    written = f"(re.union (re.++ {_NUMBER} (re.opt {_EXPONENT})) {_SPECIAL})"
    return f"(str.in_re {term} (re.++ (re.* {_SPACE}) {_SIGN} {written} (re.* {_SPACE})))"


# the strings `float_of` reads exactly: digits with an optional point, or nan and inf, after an
# optional minus
_PLAIN = (
    f'(re.++ (re.opt (str.to_re "-")) (re.union (re.++ (re.+ {_DIGIT}) (re.opt (re.++'
    f' (str.to_re ".") (re.* {_DIGIT})))) (re.++ (str.to_re ".") (re.+ {_DIGIT}))'
    ' (str.to_re "nan") (str.to_re "inf")))'
)


def _power(count: str) -> str:
    """Ten to the power ``count``, from 0 to 22, as the double that holds it exactly."""
    powers = literal(math.inf)
    for exponent in range(_EXACT_POWERS, -1, -1):
        powers = f"(ite (= {count} {exponent}) {literal(10.0**exponent)} {powers})"
    return powers


def _parts(term: str, body: str) -> str:
    """``body`` with the string's parts named: ``b!`` without its minus, ``i!`` and ``f!`` the
    digits before and after its point, ``k!`` the Int of all its digits and ``a!`` how many
    follow the point."""
    point = '(str.indexof b! "." 0)'
    before = "(ite (>= d! 0) (str.substr b! 0 d!) b!)"
    after = '(ite (>= d! 0) (str.substr b! (+ d! 1) (str.len b!)) "")'
    unsigned = f'(ite (str.prefixof "-" {term}) (str.substr {term} 1 (str.len {term})) {term})'
    counted = "((k! (str.to_int (str.++ i! f!))) (a! (str.len f!)))"
    return (
        f"(let ((b! {unsigned})) (let ((d! {point})) (let ((i! {before}) (f! {after}))"
        f" (let {counted} {body}))))"
    )


def float_of(term: str, past: str | None = None) -> tuple[str, str]:
    """Python's `float(s)` on a string it accepts, and the bound inside which the term is exact.

    Given ``past``, the term past the bound is that Float64 constant, which
    render declares for this term alone, so it can be whatever Python reads
    there.
    """
    whole = "((_ to_fp 11 53) RNE (to_real k!))"
    fraction = f"(fp.div RNE n! {_power('a!')})"
    special = f'(ite (= b! "nan") {literal(math.nan)} {literal(math.inf)})'
    number = f'(ite (or (= b! "nan") (= b! "inf")) {special} (ite (= a! 0) n! {fraction}))'
    signed = f'(ite (str.prefixof "-" {term}) (fp.neg g!) g!)'
    exact = _parts(term, f"(let ((n! {whole})) (let ((g! {number})) {signed}))")
    inside = f"(or (= a! 0) (and (<= a! {_EXACT_POWERS}) (<= k! {_EXACT_WHOLE})))"
    bound = _parts(term, f"(and (str.in_re {term} {_PLAIN}) {inside})")
    if past is None:
        return exact, bound
    return f"(ite {bound} {exact} {past})", bound
