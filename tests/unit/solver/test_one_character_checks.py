"""Each character check on one character a string's index reads, held against Python on ASCII
and against the past-ASCII kinds (known-limits S9) past it.

Two checks read the character, so its checks are written for sums to meet, as they are on each
character a loop over a string reads.
"""

from collections.abc import Callable

import pytest

from pyct.core.foundation.branch import Branch, Expression
from pyct.core.strs.str_operands import LAST_CHARACTER
from pyct.solver.answer import Sat, Unsat
from pyct.solver.checks import CHECKS
from pyct.solver.cvc5 import solve
from pyct.solver.render import program
from tests.unit.solver.agreement import SITE, needs_cvc5

# past ASCII: a letter, a digit, a mark, the soft hyphen, a space, and the last character cvc5
# holds
PAST_ASCII = ["é", "٧", "¡", "\xad", "　", chr(LAST_CHARACTER)]
CHARACTERS = [*(chr(code) for code in range(128)), *PAST_ASCII]

# past ASCII a character is no digit, letter or space, has no case and is no ASCII, and all but
# U+0080 to U+00A0 and the soft hyphen are printable
PRINTABLE_PAST_ASCII = {"é", "٧", "¡", "　", chr(LAST_CHARACTER)}

# how a path reads the character: the read, and the forks that pin it
type Reads = Callable[[str], tuple[Expression, list[Branch]]]


def expected(head: str, character: str) -> bool:
    """The check's answer: Python's on ASCII, and past ASCII the one S9 records."""
    if character.isascii():
        return getattr(character, head)()
    return head == "isprintable" and character in PRINTABLE_PAST_ASCII


def _pinned(at: int, character: str) -> tuple[Expression, list[Branch]]:
    """``s[at]``, and the fork that pins it to the character."""
    read: Expression = ["[]", "s", at]
    return read, [Branch(expression=["==", read, repr(character)], taken=True, site=SITE)]


def _letters(count: int) -> list[Branch]:
    """The forks that pin ``s``'s first letters, enough for the path to spell them."""
    return [
        Branch(expression=["==", ["[]", "s", at], repr("ab"[at])], taken=True, site=SITE)
        for at in range(count)
    ]


def at_zero(character: str) -> tuple[Expression, list[Branch]]:
    """``s[0]``, as `(str.at s 0)`, and the fork that pins it."""
    return _pinned(0, character)


def from_the_end(character: str) -> tuple[Expression, list[Branch]]:
    """``s[-1]``, a `str.at` counted back from the length, and the fork that pins it."""
    return _pinned(-1, character)


def spelled(character: str) -> tuple[Expression, list[Branch]]:
    """``s[0]`` as the first letter of a spelled ``s``, which ``s[1]`` read beside it spells,
    and the forks that pin both."""
    read, pins = _pinned(0, character)
    return read, [*pins, *_letters(2)[1:]]


def past_the_letters(character: str) -> tuple[Expression, list[Branch]]:
    """``s[6]``, too far past the letters ``s[0]`` and ``s[1]`` spell to be one, so a place in
    the rest, and the forks that pin all three."""
    read, pins = _pinned(6, character)
    return read, [*_letters(2), *pins]


READS = [at_zero, from_the_end, spelled, past_the_letters]


def _path(head: str, character: str, reads: Reads, taken: bool) -> tuple[Branch, ...]:
    """The path that asks the check on the character, on the given side, beside another."""
    read, pins = reads(character)
    other = "isdigit" if head == "isascii" else "isascii"
    beside = Branch(expression=[other, read], taken=expected(other, character), site=SITE)
    return (*pins, beside, Branch(expression=[head, read], taken=taken, site=SITE))


def asked(head: str, character: str, reads: Reads, taken: bool) -> object:
    """The answer to the check on the character, on the given side, beside another check."""
    return solve(_path(head, character, reads, taken), {"s": str}, 5.0)


@pytest.mark.parametrize("reads", READS)
def test_each_read_counts_its_character_s_kinds_as_memberships(reads: Reads) -> None:
    text = program(_path("isupper", "a", reads, False), {"s": str}).text

    assert "(ite (str.in_re " in text
    assert "str.replace_re_all" not in text
    # past the letters, the read is a place in the rest
    assert ("(str.at r!0 " in text) is (reads is past_the_letters)


# answer-a-character-check-on-a-long-string-within-the-limit-keeps-each-answer
@needs_cvc5
@pytest.mark.parametrize("reads", READS)
@pytest.mark.parametrize("head", list(CHECKS))
def test_each_check_on_one_character_keeps_its_answer(head: str, reads: Reads) -> None:
    wrong = []
    for character in CHARACTERS:
        sides = {taken: asked(head, character, reads, taken) for taken in (True, False)}
        right = expected(head, character)
        if not (isinstance(sides[right], Sat) and isinstance(sides[not right], Unsat)):
            wrong.append((character, sides))

    assert wrong == []
