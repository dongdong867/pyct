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


def at_zero(character: str) -> tuple[Expression, list[Branch]]:
    """``s[0]``, as `(str.at s 0)`, and the fork that pins it to the character."""
    read: Expression = ["[]", "s", 0]
    return read, [Branch(expression=["==", read, repr(character)], taken=True, site=SITE)]


def spelled(character: str) -> tuple[Expression, list[Branch]]:
    """``s[0]`` as the first letter of a spelled ``s``, which ``s[1]`` read beside it spells,
    and the forks that pin both."""
    read, pins = at_zero(character)
    second: Expression = ["==", ["[]", "s", 1], "'a'"]
    return read, [*pins, Branch(expression=second, taken=True, site=SITE)]


def asked(head: str, character: str, reads: Reads, taken: bool) -> object:
    """The answer to the check on the character, on the given side, beside another check."""
    read, pins = reads(character)
    other = "isdigit" if head == "isascii" else "isascii"
    beside = Branch(expression=[other, read], taken=expected(other, character), site=SITE)
    aimed = Branch(expression=[head, read], taken=taken, site=SITE)
    return solve((*pins, beside, aimed), {"s": str}, 5.0)


# answer-a-character-check-on-a-long-string-within-the-limit-keeps-each-answer
@needs_cvc5
@pytest.mark.parametrize("reads", [at_zero, spelled])
@pytest.mark.parametrize("head", list(CHECKS))
def test_each_check_on_one_character_keeps_its_answer(head: str, reads: Reads) -> None:
    wrong = []
    for character in CHARACTERS:
        sides = {taken: asked(head, character, reads, taken) for taken in (True, False)}
        right = expected(head, character)
        if not (isinstance(sides[right], Sat) and isinstance(sides[not right], Unsat)):
            wrong.append((character, sides))

    assert wrong == []
