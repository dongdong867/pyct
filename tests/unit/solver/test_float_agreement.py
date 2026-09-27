"""cvc5 held against Python on doubles: each operation render writes, and paths through them."""

import itertools
import math
import operator
import random
import struct
from collections.abc import Callable

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.floats import literal
from pyct.solver.heads import FORMS, OPERATORS
from tests.unit.solver.agreement import asked, flipped_path, heads_named, needs_cvc5, takes

# doubles at the edges of IEEE arithmetic: two that no binary fraction holds, both zeros, the
# smallest subnormal, the largest finite, the infinities and NaN, and a few plain ones
SPECIAL = [
    0.1,
    0.3,
    0.0,
    -0.0,
    2.5,
    -1.5,
    3.0,
    1e-05,
    5e-324,
    1.7976931348623157e308,
    math.inf,
    -math.inf,
    math.nan,
]


def _minus(*operands: float) -> float:
    return -operands[0] if len(operands) == 1 else operands[0] - operands[1]


# what each head render writes on doubles means in Python
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    "+": operator.add,
    "-": _minus,
    "*": operator.mul,
    "/": operator.truediv,
    "abs": abs,
    "is_integer": float.is_integer,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}
BINARY = ("+", "-", "*", "/", "<", "<=", ">", ">=", "==", "!=")
UNARY = ("-", "abs", "is_integer")
ANSWERS_A_BOOL = ("is_integer", "<", "<=", ">", ">=", "==", "!=")


def _term(head: str, operands: list[str]) -> str:
    """A head on rendered doubles, as render writes it: by its form, or by its operator."""
    form = FORMS.get((head, float))
    if form is not None:
        return form(*operands)
    return f"({OPERATORS[(head, float)]} {' '.join(operands)})"


def _cases() -> list[tuple[str, tuple[float, ...]]]:
    """Every head on every special double, or pair of them. A zero divisor raises in Python
    before the division, so it has no answer to hold cvc5 to.
    """
    pairs = list(itertools.product(SPECIAL, repeat=2))
    binary = [(head, pair) for head in BINARY for pair in pairs if head != "/" or pair[1] != 0]
    return binary + [(head, (value,)) for head in UNARY for value in SPECIAL]


def _same(said: object, meant: object) -> bool:
    """Whether two answers are one: the same truth value, or the same double to the bit.

    SMT-LIB has one NaN, so any NaN is the same as any other.
    """
    if isinstance(said, float) and isinstance(meant, float):
        both_nan = math.isnan(said) and math.isnan(meant)
        return both_nan or struct.pack(">d", said) == struct.pack(">d", meant)
    return said == meant


@needs_cvc5
def test_cvc5_agrees_with_python_to_the_bit_on_every_operation_on_special_doubles() -> None:
    cases = _cases()
    lines = ["(set-logic ALL)"]
    for at, (head, operands) in enumerate(cases):
        sort = "Bool" if head in ANSWERS_A_BOOL else "Float64"
        term = _term(head, [literal(value) for value in operands])
        lines += [f"(declare-const v{at} {sort})", f"(assert (= v{at} {term}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]

    answers = asked(lines)

    assert len(answers) == len(cases)
    disagreements = [
        (head, operands, said)
        for (head, operands), said in zip(cases, answers, strict=True)
        if not _same(said, PYTHON_HEADS[head](*operands))
    ]
    assert disagreements == []


# the literals a random path's forks compare with and compute on
PATH_LITERALS = [0.1, 0.3, 2.5, -1.5, 3.0, 1e-05, 0.0, -0.0, 1e300, math.inf, math.nan]

# where a random path's x starts, and more doubles an unsat answer is checked against
SEEDS = [0.0, -0.0, 1.5, -2.5, 0.1, 7.0, 1e300, 5e-324, -1e-300]
WITNESSES = [*SPECIAL, *SEEDS, 0.2, 0.19999999999999998, 4.0, -3.0, 1e-300]


def _step(rng: random.Random, term: Expression, divided: bool) -> tuple[Expression, bool]:
    """One more operation on the term, and whether it divides by the term, which records a fork.

    Only one step of a path's term divides by it, so a condition has one zero fork at most.
    """
    other = rng.choice([value for value in PATH_LITERALS if value != 0])
    choice = rng.randrange(8 if divided else 9)
    steps: list[Expression] = [
        ["+", term, other],
        ["-", term, other],
        ["-", other, term],
        ["*", term, other],
        ["/", term, other],
        ["-", term],
        ["abs", term],
        ["+", term, term],
        ["/", other, term],
    ]
    return steps[choice], choice == 8


def _condition(rng: random.Random) -> tuple[Expression, Expression | None]:
    """A random condition on x, and the zero fork its division records first, if any."""
    term: Expression = "x"
    guard: Expression | None = None
    for _ in range(rng.randint(0, 2)):
        divisor = term
        term, divides = _step(rng, term, guard is not None)
        guard = ["!=", divisor, 0.0] if divides else guard
    kind = rng.random()
    if kind < 0.15:
        return ["is_integer", term], guard
    if kind < 0.3:
        return ["!=", term, 0.0], guard
    op = rng.choice(["<", "<=", ">", ">=", "==", "!="])
    return [op, term, rng.choice(PATH_LITERALS)], guard


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some x takes through random conditions, the last one flipped."""
    conditions = [_condition(rng) for _ in range(rng.randint(1, 4))]
    return flipped_path(rng.choice(SEEDS), conditions, PYTHON_HEADS, name="x")


def _disagrees(path: tuple[Branch, ...], answer: object) -> bool:
    """Whether Python disagrees: a model off the path, or an unsat a witness takes the path of."""
    if isinstance(answer, Sat):
        return not takes(path, answer.model["x"], PYTHON_HEADS, name="x")
    if isinstance(answer, Unsat):
        return any(takes(path, value, PYTHON_HEADS, name="x") for value in WITNESSES)
    return False


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_float_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [_flipped_path(rng) for _ in range(60)]

    answers = [solve(path, {"x": float}, 2.0) for path in paths]

    # an error is cvc5 failing to answer at all, which is never agreement
    assert [answer for answer in answers if isinstance(answer, Error)] == []
    # the paths cvc5 answered reach every head, so a clean result is not a narrow one
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    assert set().union(*(heads_named(path, PYTHON_HEADS) for path in answered)) == set(PYTHON_HEADS)
    # a timeout or an unknown is a miss, which the run reports as one; only an answer can be
    # wrong
    wrong = [path for path, answer in zip(paths, answers, strict=True) if _disagrees(path, answer)]
    assert wrong == []
