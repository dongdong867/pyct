"""The character checks in SMT-LIB, and cvc5 held against Python on them."""

import operator
import random

from pyct.core.branch import Branch
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.checks import CHECKS, KINDS, outside
from pyct.solver.cvc5 import solve
from pyct.solver.strings import encode
from tests.unit.solver.agreement import SITE, ascii_disagrees, asked, heads_named, needs_cvc5
from tests.unit.solver.test_render import render

# every ASCII character
ASCII = [chr(code) for code in range(128)]

# the checks as Python has them
PYTHON_HEADS = {head: operator.methodcaller(head) for head in CHECKS}


def test_the_kinds_are_apart_and_hold_every_character() -> None:
    runs = sorted(run for ranges in KINDS.values() for run in ranges)

    # each run starts where the one before it stops, from U+0000 to the last cvc5 holds
    assert outside(tuple(runs)) == ()
    assert all(before[1] + 1 == after[0] for before, after in zip(runs, runs[1:], strict=False))


def _program(values: list[str]) -> tuple[list[str], list[bool]]:
    """One program asking every check of every value, and Python's answers."""
    lines = ["(set-logic ALL)"]
    python: list[bool] = []
    for at, value in enumerate(values):
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        for head, check in CHECKS.items():
            answer, fact = check(f"s{at}")
            asked_at = len(python)
            lines += [f"(declare-const v{asked_at} Bool)", f"(assert (= v{asked_at} {answer}))"]
            lines.append(f"(assert {fact})")
            python.append(getattr(value, head)())
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(python)))}))"]
    return lines, python


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_check_of_an_ascii_string() -> None:
    rng = random.Random(0)
    # every ASCII character alone, then random strings of them, most of them letters and digits
    common = list("aAzZ09_ \t")
    values = ASCII + ["".join(rng.choices(common + ASCII, k=rng.randint(0, 6))) for _ in range(150)]
    lines, python = _program(values)

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
def test_a_character_past_ascii_is_in_no_class_and_printable_as_the_table_says() -> None:
    values = list(PAST_ASCII_ANSWERS)
    lines, _ = _program(values)

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
