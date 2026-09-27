"""What the tests that hold cvc5 against Python share.

cvc5 is asked the value of fixed terms, a random path is walked in Python
with its last fork flipped, and an answer is judged against Python. A test
names the heads its paths use and what each means in Python.
"""

import ast
import itertools
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Answer, Sat, Unsat
from pyct.solver.strings import decode

SITE = Site("m.py", 2, 7)

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

# the characters random fixed strings are made of: ASCII letters, the edges of what cvc5 holds,
# a letter past ASCII, a lone surrogate and an emoji
ALPHABET = ["a", "b", "z", "\x00", "\x7f", "é", "\ud800", "\U0001f600", "\U0002ffff"]

# the letters of a random path's strings: two ASCII letters and one past ASCII
PATH_LETTERS = ["a", "b", "é"]

# what each head a test's paths use means in Python
type Heads = Mapping[str, Callable[..., object]]

# one value cvc5 prints for an asked `vN`: a negative Int, an Int, a Bool, or a String literal
_VALUE = re.compile(r'\(v\d+ (\(- \d+\)|\d+|true|false|"(?:[^"]|"")*")\)')


def asked(lines: list[str]) -> list[object]:
    """What cvc5 says each asked value is, in order, as the Python value it stands for."""
    answer = subprocess.run(
        ["cvc5", "--produce-models", "--lang", "smt", "--quiet"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert answer.startswith("sat"), answer
    return [_read(value) for value in _VALUE.findall(answer)]


def _read(value: str) -> object:
    """A Bool, an Int or a String as cvc5 prints it."""
    if value in ("true", "false"):
        return value == "true"
    if value.startswith('"'):
        return decode(value)
    return -int(value[len("(- ") : -1]) if value.startswith("(") else int(value)


def python(expression: Expression, s: str, heads: Heads) -> object:
    """What Python makes of a condition on s. A leaf is s, a literal, a number, or None.

    A part the condition holds in more than one place is worked out once, so
    a condition that doubles written out costs one step per distinct part.
    """
    values: dict[int, object] = {}

    def value(part: Expression) -> object:
        if isinstance(part, list):
            if id(part) not in values:
                head, *operands = part
                assert isinstance(head, str)
                values[id(part)] = heads[head](*(value(operand) for operand in operands))
            return values[id(part)]
        if isinstance(part, str):
            return s if part == "s" else ast.literal_eval(part)
        return part

    return value(expression)


def flipped_path(
    s: str, conditions: Iterable[tuple[Expression, Expression | None]], heads: Heads
) -> tuple[Branch, ...]:
    """The forks s takes through the conditions, the last one flipped.

    A condition may come with the fork an operation records before it may
    raise; s stops at the first of those it does not take, as the target
    would. That is the question a run asks the solver: every fork before the
    last is one a real input took, so only the flip can make it unsat.
    """
    forks: list[Branch] = []
    for condition, guard in conditions:
        if guard is not None:
            forks.append(Branch(expression=guard, taken=bool(python(guard, s, heads)), site=SITE))
            if not forks[-1].taken:
                break
        forks.append(
            Branch(expression=condition, taken=bool(python(condition, s, heads)), site=SITE)
        )
    last = forks[-1]
    return (*forks[:-1], Branch(expression=last.expression, taken=not last.taken, site=SITE))


def takes(path: tuple[Branch, ...], s: str, heads: Heads) -> bool:
    """Whether s takes every fork of the path the way the plan says."""
    return all(bool(python(fork.expression, s, heads)) == fork.taken for fork in path)


def disagrees(
    path: tuple[Branch, ...], answer: Answer, heads: Heads, letters: list[str], longest: int
) -> bool:
    """Whether Python disagrees with an answer: a model off the plan, or an unsat with a witness.

    A witness is looked for among the strings of up to ``longest`` of the
    letters, so an unsat is checked as far as that reaches.
    """
    if isinstance(answer, Sat):
        s = answer.model["s"]
        assert isinstance(s, str)
        return not takes(path, s, heads)
    if isinstance(answer, Unsat):
        short = (
            "".join(p) for k in range(longest + 1) for p in itertools.product(letters, repeat=k)
        )
        return any(takes(path, s, heads) for s in short)
    return False


def heads_named(path: tuple[Branch, ...], heads: Iterable[str]) -> set[str]:
    """Every one of the heads that a path's forks name."""
    return {head for fork in path for head in heads if f"'{head}'" in str(fork.expression)}
