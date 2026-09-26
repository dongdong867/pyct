"""The searches in SMT-LIB: the terms strings.py writes, and cvc5 held against Python on them."""

import ast
import itertools
import operator
import random
import re
import shutil
import subprocess
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Answer, Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import (
    contains,
    encode,
    ends_with,
    first_index,
    last_index,
    occurrences,
    starts_with,
)

SITE = Site("m.py", 2, 7)

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

# the characters the random strings are made of: ASCII letters, the edges of what cvc5 holds,
# a letter past ASCII, a lone surrogate and an emoji
ALPHABET = ["a", "b", "z", "\x00", "\x7f", "é", "\ud800", "\U0001f600", "\U0002ffff"]


def test_a_last_index_reads_a_literal_substring_reversed_as_a_literal() -> None:
    # the first place the reversed substring starts in the reversed string, counted back from
    # the end, held at or above the first index
    back = '(- (- (str.len s) 2) (str.indexof (str.rev s) "ba" 0))'
    first = '(str.indexof s "ab" 0)'

    assert last_index("s", '"ab"') == (
        f'(ite (str.contains s "ab") (ite (< {back} {first}) {first} {back}) (- 1))'
    )


def test_a_count_reads_a_literal_substring_reversed_as_a_literal() -> None:
    # every substring removed from the reversed string, and what went divided by its length
    counted = '(div (- (str.len s) (str.len (str.replace_all (str.rev s) "ba" ""))) 2)'

    assert occurrences("s", '"ab"') == (
        '(ite (= "ab" "") (+ (str.len s) 1)'
        f' (ite (str.contains s "ab") (ite (< {counted} 1) 1 {counted}) 0))'
    )


def test_a_tracked_substring_is_reversed_and_measured_by_cvc5() -> None:
    assert "(str.indexof (str.rev s) (str.rev t) 0)" in last_index("s", "t")
    assert "(- (- (str.len s) (str.len t))" in last_index("s", "t")
    assert '(str.replace_all (str.rev s) (str.rev t) "")' in occurrences("s", "t")


def test_a_literal_is_reversed_character_by_character() -> None:
    # a double quote and a character past ASCII are one character each, whatever their spelling
    written = last_index("s", encode('a"é'))

    assert f"(str.indexof (str.rev s) {encode('é' + '"' + 'a')} 0)" in written
    assert "(- (- (str.len s) 3)" in written


# every search, the Python it has to agree with, and the sort of its answer. Each form takes
# its operands in the expression's order, which puts the needle first for `in` alone
PYTHON_SEARCHES: dict[str, tuple[Callable[[str, str], str], Callable[[str, str], object], str]] = {
    "in": (lambda s, sub: contains(sub, s), lambda s, sub: sub in s, "Bool"),
    "startswith": (starts_with, str.startswith, "Bool"),
    "endswith": (ends_with, str.endswith, "Bool"),
    "find": (first_index, str.find, "Int"),
    "rfind": (last_index, str.rfind, "Int"),
    "count": (occurrences, str.count, "Int"),
}


def _search_cases(count: int) -> list[tuple[str, str, str, bool]]:
    """Random (value, head, substring, tracked) cases, fixed by the seed.

    Half the substrings are cut from the value, so a search finds as often
    as it misses; a tracked substring is a constant cvc5 reverses itself.
    """
    rng = random.Random(0)
    cases = []
    for _ in range(count):
        value = "".join(rng.choices(ALPHABET, k=rng.randint(0, 5)))
        sub = "".join(rng.choices(ALPHABET, k=rng.randint(0, 2)))
        if value and rng.random() < 0.5:
            start = rng.randint(0, len(value) - 1)
            sub = value[start : start + rng.randint(0, 2)]
        cases.append((value, rng.choice(list(PYTHON_SEARCHES)), sub, rng.random() < 0.3))
    return cases


def _program(cases: list[tuple[str, str, str, bool]]) -> list[str]:
    """One program asking the answer of every case.

    Each value is a constant held equal to its literal, so the string reaches
    the form as a name, the way a tracked parameter does.
    """
    lines = ["(set-logic ALL)"]
    for at, (value, head, sub, tracked) in enumerate(cases):
        form, _, sort = PYTHON_SEARCHES[head]
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        needle = encode(sub)
        if tracked:
            lines += [f"(declare-const t{at} String)", f"(assert (= t{at} {needle}))"]
            needle = f"t{at}"
        lines += [f"(declare-const v{at} {sort})", f"(assert (= v{at} {form(f's{at}', needle)}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]
    return lines


def _answers(lines: list[str]) -> list[object]:
    """What cvc5 says each asked value is, in order: a Bool or an Int apiece."""
    answer = subprocess.run(
        ["cvc5", "--produce-models", "--lang", "smt", "--quiet"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert answer.startswith("sat"), answer
    return [_read(value) for value in re.findall(r"\(v\d+ (\(- \d+\)|\d+|true|false)\)", answer)]


def _read(value: str) -> object:
    """A Bool or an Int as cvc5 prints it."""
    if value in ("true", "false"):
        return value == "true"
    return -int(value[len("(- ") : -1]) if value.startswith("(") else int(value)


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_search() -> None:
    cases = _search_cases(400)

    answers = _answers(_program(cases))

    # every value is fixed, so cvc5 only works each term out: this holds the terms to Python
    python = [PYTHON_SEARCHES[head][1](value, sub) for value, head, sub, _ in cases]
    assert len(answers) == len(cases)
    disagreements = [
        (case, said, meant)
        for case, said, meant in zip(cases, answers, python, strict=True)
        if said != meant
    ]
    assert disagreements == []


# what each head on a search path means in Python, to hold a model against the plan
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    "in": lambda sub, s: sub in s,
    "startswith": str.startswith,
    "endswith": str.endswith,
    "find": str.find,
    "index": str.index,
    "rfind": str.rfind,
    "rindex": str.rindex,
    "count": str.count,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">=": operator.ge,
}

# the searches a random path picks from, and the letters of its substrings: two ASCII letters
# and one past ASCII
SEARCH_HEADS = ["in", "startswith", "endswith", "find", "index", "rfind", "rindex", "count"]
PATH_LETTERS = ["a", "b", "é"]


def _python(expression: Expression, s: str) -> object:
    """What Python makes of a condition on s. A leaf is s, a literal, or a number."""
    if isinstance(expression, list):
        head, left, right = expression
        assert isinstance(head, str)
        return PYTHON_HEADS[head](_python(left, s), _python(right, s))
    if isinstance(expression, str):
        return s if expression == "s" else ast.literal_eval(expression)
    return expression


def _search_fork(rng: random.Random) -> tuple[Expression, Expression | None]:
    """One random search fork, and the `in` fork a raising search records before it, if any."""
    head = rng.choice(SEARCH_HEADS)
    sub = repr("".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 2))))
    if head == "in":
        return ["in", sub, "s"], None
    if head in ("startswith", "endswith"):
        return [head, "s", sub], None
    another: list[Expression] = [rng.choice(["find", "rfind", "count"]), "s", sub]
    other: Expression = rng.choice([rng.randint(-1, 3), another])
    compare: list[Expression] = [rng.choice(["==", "!=", "<", ">="]), [head, "s", sub], other]
    return compare, (["in", sub, "s"] if head in ("index", "rindex") else None)


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some string takes through random searches, the last one flipped.

    That is the question a run asks the solver: every fork before the last
    is one a real input took, so only the flip can make it unsat.
    """
    s = "".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 5)))
    forks: list[Branch] = []
    for _ in range(rng.randint(1, 6)):
        expression, found = _search_fork(rng)
        if found is not None:
            forks.append(Branch(expression=found, taken=bool(_python(found, s)), site=SITE))
            if not forks[-1].taken:
                break
        forks.append(Branch(expression=expression, taken=bool(_python(expression, s)), site=SITE))
    last = forks[-1]
    return (*forks[:-1], Branch(expression=last.expression, taken=not last.taken, site=SITE))


def _takes(path: tuple[Branch, ...], s: str) -> bool:
    """Whether s takes every fork of the path the way the plan says."""
    return all(bool(_python(fork.expression, s)) == fork.taken for fork in path)


def _disagrees(path: tuple[Branch, ...], answer: Answer) -> bool:
    """Whether Python disagrees with an answer: a model off the plan, or an unsat with a witness.

    A witness is looked for among the strings of up to four of the path's
    letters and one more, so an unsat is checked as far as that reaches.
    """
    if isinstance(answer, Sat):
        s = answer.model["s"]
        assert isinstance(s, str)
        return not _takes(path, s)
    if isinstance(answer, Unsat):
        written = "".join(str(fork.expression) for fork in path)
        letters = [letter for letter in PATH_LETTERS if letter in written] + ["z"]
        short = ("".join(p) for k in range(5) for p in itertools.product(letters, repeat=k))
        return any(_takes(path, s) for s in short)
    return False


def _heads(path: tuple[Branch, ...]) -> set[str]:
    """Every search head a path's forks name."""
    return {head for fork in path for head in SEARCH_HEADS if f"'{head}'" in str(fork.expression)}


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_search_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [_flipped_path(rng) for _ in range(40)]

    answers = [solve(path, {"s": str}, 1.0) for path in paths]

    # an error is cvc5 failing to answer at all, which is never agreement
    assert [answer for answer in answers if isinstance(answer, Error)] == []
    # the paths cvc5 answered reach every search, so a clean result is not a narrow one
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    assert set().union(*(_heads(path) for path in answered)) == set(SEARCH_HEADS)
    # a timeout or an unknown is a miss, which the run reports as one; only an answer can be
    # wrong, so a miss fails this test only by leaving a search unanswered
    wrong = [path for path, answer in zip(paths, answers, strict=True) if _disagrees(path, answer)]
    assert wrong == []
