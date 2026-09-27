"""The character checks in SMT-LIB, and cvc5 held against Python on them."""

import operator
import random
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.checks import CHECKS, KINDS, Check, membership, outside
from pyct.solver.cvc5 import solve
from pyct.solver.strings import encode
from tests.unit.solver.agreement import SITE, ascii_disagrees, asked, heads_named, needs_cvc5
from tests.unit.solver.test_render import render

# every ASCII character
ASCII = [chr(code) for code in range(128)]

# the checks as Python has them
PYTHON_HEADS = {head: operator.methodcaller(head) for head in CHECKS}

# how a program writes one check on one string: the answer, and the fact it asserts beside it
type Form = Callable[[str, str], Check]


def counts(head: str, term: str) -> Check:
    """The check as counts of character kinds, the form for a string two checks read."""
    return CHECKS[head](term)


def alone(head: str, term: str) -> Check:
    """The check as one membership, the form for a string no other check reads."""
    return membership(head, term), "true"


FORMS = pytest.mark.parametrize("form", [counts, alone])


def test_the_kinds_are_apart_and_hold_every_character() -> None:
    runs = sorted(run for ranges in KINDS.values() for run in ranges)

    # each run starts where the one before it stops, from U+0000 to the last cvc5 holds
    assert outside(tuple(runs)) == ()
    assert all(before[1] + 1 == after[0] for before, after in zip(runs, runs[1:], strict=False))


def _program(values: list[str], form: Form) -> tuple[list[str], list[bool]]:
    """One program asking every check of every value in one form, and Python's answers."""
    lines = ["(set-logic ALL)"]
    python: list[bool] = []
    for at, value in enumerate(values):
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        for head in CHECKS:
            answer, fact = form(head, f"s{at}")
            asked_at = len(python)
            lines += [f"(declare-const v{asked_at} Bool)", f"(assert (= v{asked_at} {answer}))"]
            lines.append(f"(assert {fact})")
            python.append(getattr(value, head)())
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(python)))}))"]
    return lines, python


@needs_cvc5
@FORMS
def test_cvc5_agrees_with_python_on_every_check_of_an_ascii_string(form: Form) -> None:
    rng = random.Random(0)
    # every ASCII character alone, then random strings of them, most of them letters and digits
    common = list("aAzZ09_ \t")
    values = ASCII + ["".join(rng.choices(common + ASCII, k=rng.randint(0, 6))) for _ in range(150)]
    lines, python = _program(values, form)

    assert asked(lines) == python


# a string past ASCII and what each check says of it here: a character past ASCII is no digit,
# letter or space and has no case, isascii is exact, and isprintable exact up to U+00FF
PAST_ASCII_ANSWERS = {
    "é": {"isprintable": True},
    "²": {"isprintable": True},
    "\x85": {},
    "\xa0": {},
    "\xad": {},
    "\xa1": {"isprintable": True},
    "\u2028": {"isprintable": True},
}


@needs_cvc5
@FORMS
def test_a_character_past_ascii_is_in_no_class_and_printable_as_the_table_says(form: Form) -> None:
    values = list(PAST_ASCII_ANSWERS)
    lines, _ = _program(values, form)

    answers = asked(lines)

    expected = [PAST_ASCII_ANSWERS[value].get(head, False) for value in values for head in CHECKS]
    assert answers == expected


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some string takes through random checks, the last one flipped."""
    s = "".join(rng.choices(list("aAzZ09 _\t!\x00\x1f~é"), k=rng.randint(0, 4)))
    heads = rng.sample(list(CHECKS), rng.randint(1, len(CHECKS)))
    forks = [Branch(expression=[head, "s"], taken=getattr(s, head)(), site=SITE) for head in heads]
    last = forks[-1]
    return (*forks[:-1], Branch(expression=last.expression, taken=not last.taken, site=SITE))


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_check_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [_flipped_path(rng) for _ in range(40)]

    answers = [solve(path, {"s": str}, 2.0) for path in paths]

    assert [answer for answer in answers if isinstance(answer, Error)] == []
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    assert set().union(*(heads_named(path, CHECKS) for path in answered)) == set(CHECKS)
    # a timeout or an unknown is a miss; only an answer can be wrong, and only for ASCII
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if ascii_disagrees(path, answer, PYTHON_HEADS, list("aA0 _!\t"), 3)
    ]
    assert wrong == []


def test_two_checks_on_one_string_state_its_counts_once() -> None:
    prefix = (
        Branch(expression=["isdigit", "s"], taken=False, site=SITE),
        Branch(expression=["isalpha", "s"], taken=True, site=SITE),
    )

    lines = render(prefix, {"s": str}).splitlines()

    _, fact = CHECKS["isdigit"]("|arg.s|")
    assert lines.count(f"(assert {fact})") == 1


def test_a_string_one_check_reads_is_asked_as_one_membership() -> None:
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=["isdigit", "s"], taken=False, site=SITE),
    )

    text = render(prefix, {"s": str})

    assert f"(assert {membership('isdigit', '|arg.s|')})" in text
    assert "str.replace_re_all" not in text


def test_a_check_on_another_string_leaves_this_one_a_membership() -> None:
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=["isalpha", "t"], taken=True, site=SITE),
    )

    text = render(prefix, {"s": str, "t": str})

    assert f"(assert {membership('isdigit', '|arg.s|')})" in text
    assert f"(assert {membership('isalpha', '|arg.t|')})" in text


@needs_cvc5
def test_a_long_string_one_check_reads_is_answered_inside_the_limit() -> None:
    """The card number's case: digits, at least 13 of them, and not a 4 first."""
    prefix = (
        Branch(expression=["isdigit", "s"], taken=True, site=SITE),
        Branch(expression=["<", ["len", "s"], 13], taken=False, site=SITE),
        Branch(expression=["startswith", "s", "'4'"], taken=False, site=SITE),
    )

    answer = solve(prefix, {"s": str}, 5.0)

    assert isinstance(answer, Sat), answer
    number = answer.model["s"]
    assert isinstance(number, str) and number.isdigit(), answer
    assert len(number) >= 13 and not number.startswith("4"), answer
