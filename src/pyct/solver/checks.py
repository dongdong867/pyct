"""Python's character checks in SMT-LIB: on a string one check reads, one regular expression
membership; on a string two or more read, counts of how many characters of each kind it has.

A check asks what kind each character of a string is: a digit, a letter, a
space, and so on. The characters cvc5 holds are split into kinds that do not
overlap (`KINDS`), and each check is a condition on how many characters of
each kind the string has: ``isalpha`` is "a letter, and every character an
uppercase or a lowercase letter". The count of a kind is the length the
string loses when its characters of that kind are removed. Written so, two
checks on one string meet as sums, which cvc5 settles at once, where it ran
paths of a few regular expression memberships to its time limit. A check
also states the fact that the counts add up to the string's length (see
`counted`), which cvc5 does not work out from the removals.

A count costs cvc5 more the longer the string must be: a digit string of at
least 13 characters ran past 10 s. So a string only one check reads, where
no sums have anything to meet, is asked as one regular expression
membership instead (see `check`), which gives the same answer.

A loop over a string reads each character as ``s[i]``, a string of at most
one character, and two checks on each wrote ten removals a character: from a
16-character seed, `camel_to_snake_case`'s ask for a character that is not
alphanumeric ran to cvc5's 10 s limit, and from a 64-character seed too. On
such a string each count is written as one membership instead,
``(ite (str.in_re c K) 1 0)``, which is the removal's count there, and the
fact that the counts add up to the length holds of itself. The same two asks
then answer sat in 0.04 s and 0.23 s (cvc5 1.3.4).

Each kind is exact for ASCII. Past ASCII, a character is no digit, no letter
and no space, and it has no case, as cvc5's ``str.to_upper`` and
``str.to_lower`` leave it; U+0080 to U+00A0 and the soft hyphen are not
printable and the rest are. So ``"é".isalpha()`` is false here where Python
says true, and the run reports an input like that as one that left the
plan. ``isascii`` is exact for every character.
"""

from collections.abc import Callable, Iterable, Mapping

from pyct.core.strs.str_operands import LAST_CHARACTER
from pyct.solver.dag import Node
from pyct.solver.letters import Key, Keyed
from pyct.solver.strings import encode, length

# a class of characters: runs of code points, each from its first to its last, in order
type Ranges = tuple[tuple[int, int], ...]

# a check: the term that gives Python's answer, and a fact that holds of the string whatever
# the answer is, for render to assert once
type Check = tuple[str, str]

# how a check counts the characters of a string that are of some kinds
type Count = Callable[[str, Iterable[str]], str]

DIGITS: Ranges = ((0x30, 0x39),)
UPPER: Ranges = ((0x41, 0x5A),)
LOWER: Ranges = ((0x61, 0x7A),)
LETTERS: Ranges = (*UPPER, *LOWER)
# tab to carriage return and the four separators \x1c to \x1f: whitespace but the space
_BLANKS: Ranges = ((0x09, 0x0D), (0x1C, 0x1F))
_SPACE_ITSELF: Ranges = ((0x20, 0x20),)


def _joined(ranges: Ranges) -> Ranges:
    """The runs in order, each joined to the next where the two meet, so a regex has fewer."""
    runs: list[tuple[int, int]] = []
    for first, last in sorted(ranges):
        if runs and first <= runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], max(last, runs[-1][1]))
        else:
            runs.append((first, last))
    return tuple(runs)


# what isspace takes, and what strip and split() take away: one set, as in Python
SPACE: Ranges = _joined((*_BLANKS, *_SPACE_ITSELF))

# the kinds of character, apart from each other and together every character cvc5 holds
KINDS: Mapping[str, Ranges] = {
    "digit": DIGITS,
    "upper": UPPER,
    "lower": LOWER,
    "underscore": ((0x5F, 0x5F),),
    "space": _SPACE_ITSELF,
    "whitespace_but_space": _BLANKS,
    "punctuation_but_underscore": (
        (0x21, 0x2F),
        (0x3A, 0x40),
        (0x5B, 0x5E),
        (0x60, 0x60),
        (0x7B, 0x7E),
    ),
    "control_but_whitespace": ((0x00, 0x08), (0x0E, 0x1B), (0x7F, 0x7F)),
    "unprintable_past_ascii": ((0x80, 0xA0), (0xAD, 0xAD)),
    "printable_past_ascii": ((0xA1, 0xAC), (0xAE, LAST_CHARACTER)),
}


def outside(ranges: Ranges) -> Ranges:
    """Every character cvc5 holds that the class leaves out, as runs in order."""
    runs: list[tuple[int, int]] = []
    start = 0
    for first, last in sorted(ranges):
        if first > start:
            runs.append((start, first - 1))
        start = max(start, last + 1)
    if start <= LAST_CHARACTER:
        runs.append((start, LAST_CHARACTER))
    return tuple(runs)


def of(characters: Iterable[str]) -> Ranges:
    """The class of the given characters, each its own run."""
    return tuple((ord(character), ord(character)) for character in sorted(set(characters)))


def one_of(ranges: Ranges) -> str:
    """The regular expression that matches one character of the class, which has one run at
    least."""
    parts = [f"(re.range {encode(chr(first))} {encode(chr(last))})" for first, last in ranges]
    return parts[0] if len(parts) == 1 else f"(re.union {' '.join(parts)})"


def _summed(counts: list[str]) -> str:
    """The sum of the counts, one count or more."""
    return counts[0] if len(counts) == 1 else f"(+ {' '.join(counts)})"


def _removed(term: str, kinds: Iterable[str]) -> str:
    """How many characters of the term are of the kinds: the sum of each kind's count, the
    length the term loses when that kind is removed."""
    return _summed(
        [
            f'(- {length(term)} (str.len (str.replace_re_all {term} {one_of(KINDS[kind])} "")))'
            for kind in kinds
        ]
    )


def _held(term: str, kinds: Iterable[str]) -> str:
    """How many characters of a term of at most one character are of the kinds: the sum of
    each kind's count, 1 where the term is a character of that kind and else 0."""
    return _summed([f"(ite (str.in_re {term} {one_of(KINDS[kind])}) 1 0)" for kind in kinds])


def counted(term: str) -> str:
    """The fact every string meets: its counts are each zero or more, and add up to its length."""
    each = [f"(>= {_removed(term, [kind])} 0)" for kind in KINDS]
    return f"(and (= {_removed(term, KINDS)} {length(term)}) {' '.join(each)})"


def _all(term: str, kinds: Iterable[str], count: Count) -> str:
    """The term has a character, and every character is of the kinds."""
    return f"(and (> {length(term)} 0) (= {count(term, kinds)} {length(term)}))"


def _none(term: str, kinds: Iterable[str], count: Count) -> str:
    """No character of the term is of the kinds."""
    return f"(= {count(term, kinds)} 0)"


def _cased(term: str, cased: str, other: str, count: Count) -> str:
    """A letter of one case, and none of the other: ``isupper`` and ``islower``."""
    return f"(and (> {count(term, [cased])} 0) {_none(term, [other], count)})"


# a run of letters as istitle and title want it: one uppercase letter, then lowercase ones
_WORD = f"(re.++ {one_of(UPPER)} (re.* {one_of(LOWER)}))"
NOT_LETTER = one_of(outside(LETTERS))

# a string whose runs of letters each start uppercase and go on lowercase, a run apart from the
# next: what title makes. A string with no letter is one
TITLE_CASED = (
    f"(re.++ (re.* {NOT_LETTER}) (re.* (re.++ {_WORD} (re.+ {NOT_LETTER}))) (re.opt {_WORD}))"
)

# the same with one run at least
_TITLED = (
    f"(re.++ (re.* {NOT_LETTER}) {_WORD} (re.* (re.++ (re.+ {NOT_LETTER}) {_WORD}))"
    f" (re.* {NOT_LETTER}))"
)


def _titled(term: str, count: Count) -> str:
    """``s.istitle()``: each run of letters one uppercase letter and then lowercase ones.

    At least one run, so an uppercase letter, which is said as a count too
    for the checks around it to meet.
    """
    return f"(and (str.in_re {term} {_TITLED}) (> {count(term, ['upper'])} 0))"


def _identifier(term: str, count: Count) -> str:
    """``s.isidentifier()``: letters, digits and underscores, and no digit first."""
    named = _all(term, ["digit", "upper", "lower", "underscore"], count)
    return f"(and {named} (not (str.in_re (str.at {term} 0) {one_of(DIGITS)})))"


# the kinds past ASCII, and the kinds isprintable says no to
_PAST_ASCII = ["unprintable_past_ascii", "printable_past_ascii"]
_UNPRINTABLE = ["whitespace_but_space", "control_but_whitespace", "unprintable_past_ascii"]


# each character check, as the term that gives Python's answer for ASCII. isdigit, isdecimal
# and isnumeric part only past ASCII, where each has characters the others do not
_ANSWERS: Mapping[str, Callable[[str, Count], str]] = {
    "isdigit": lambda term, count: _all(term, ["digit"], count),
    "isdecimal": lambda term, count: _all(term, ["digit"], count),
    "isnumeric": lambda term, count: _all(term, ["digit"], count),
    "isalpha": lambda term, count: _all(term, ["upper", "lower"], count),
    "isalnum": lambda term, count: _all(term, ["digit", "upper", "lower"], count),
    "isspace": lambda term, count: _all(term, ["space", "whitespace_but_space"], count),
    "isupper": lambda term, count: _cased(term, "upper", "lower", count),
    "islower": lambda term, count: _cased(term, "lower", "upper", count),
    "isascii": lambda term, count: _none(term, _PAST_ASCII, count),
    "isprintable": lambda term, count: _none(term, _UNPRINTABLE, count),
    "istitle": _titled,
    "isidentifier": _identifier,
}


def _checked(answer: Callable[[str, Count], str]) -> Callable[[str], Check]:
    """A check's answer as removal counts, with the fact about its string's counts."""
    return lambda term: (answer(term, _removed), counted(term))


# each character check as removal counts: the term for Python's answer, and the fact about the
# counts it reads
CHECKS: Mapping[str, Callable[[str], Check]] = {
    head: _checked(answer) for head, answer in _ANSWERS.items()
}


def _runs(kinds: Iterable[str]) -> Ranges:
    """The characters of the kinds, as runs in order."""
    return _joined(tuple(run for kind in kinds for run in KINDS[kind]))


def _in(kinds: Iterable[str]) -> str:
    """The regular expression that matches one character of the kinds."""
    return one_of(_runs(kinds))


def _not_in(kinds: Iterable[str]) -> str:
    """The regular expression that matches one character of none of the kinds."""
    return one_of(outside(_runs(kinds)))


def _one_of_case(cased: str, other: str) -> str:
    """A letter of one case at least, and none of the other, as a regular expression."""
    rest = f"(re.* {_not_in([other])})"
    return f"(re.++ {rest} {_in([cased])} {rest})"


# one or more ASCII digits: what `isdigit` holds alone, and a string `int` reads
ALL_DIGITS = f"(re.+ {_in(['digit'])})"

# each check as the one regular expression a string matches exactly where the check's counts
# say true
_MEMBERSHIPS: Mapping[str, str] = {
    "isdigit": ALL_DIGITS,
    "isdecimal": ALL_DIGITS,
    "isnumeric": ALL_DIGITS,
    "isalpha": f"(re.+ {_in(['upper', 'lower'])})",
    "isalnum": f"(re.+ {_in(['digit', 'upper', 'lower'])})",
    "isspace": f"(re.+ {_in(['space', 'whitespace_but_space'])})",
    "isupper": _one_of_case("upper", "lower"),
    "islower": _one_of_case("lower", "upper"),
    "isascii": f"(re.* {_not_in(_PAST_ASCII)})",
    "isprintable": f"(re.* {_not_in(_UNPRINTABLE)})",
    "istitle": _TITLED,
    "isidentifier": (
        f"(re.++ {_in(['upper', 'lower', 'underscore'])}"
        f" (re.* {_in(['digit', 'upper', 'lower', 'underscore'])}))"
    ),
}


def membership(head: str, term: str) -> str:
    """The check on the term as one regular expression membership, true where its counts are."""
    return f"(str.in_re {term} {_MEMBERSHIPS[head]})"


def check(head: str, term: str, *, alone: bool, character: bool) -> Check:
    """The check on the term: a membership when ``alone``, no other check reading the string,
    and otherwise counts, for the checks on one string to meet as sums.

    A ``character`` is a string of at most one character, as ``s[i]`` hands one out: each
    count there is one membership, and their fact holds of itself. Any other string's counts
    are removals, with their fact.
    """
    if alone:
        return membership(head, term), "true"
    return (_ANSWERS[head](term, _held), "true") if character else CHECKS[head](term)


def checks_by_string(order: Iterable[Node], key: Keyed) -> dict[Key, set[str]]:
    """The checks the path reads on each string, by the string's key."""
    heads: dict[Key, set[str]] = {}
    for node in order:
        head = node[0]
        if isinstance(head, str) and head in CHECKS and (string := key(node[1])) is not None:
            heads.setdefault(string, set()).add(head)
    return heads
