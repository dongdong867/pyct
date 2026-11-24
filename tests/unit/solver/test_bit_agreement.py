"""cvc5 held against Python on an int's bit operations: `&`, `|`, `^`, `~`, `<<` and `>>`."""

import operator
import random
from collections.abc import Callable

import pytest

from pyct.core.foundation.branch import Branch, Expression
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.given import argv, options
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_cvc5 import fork

OPERATIONS: dict[str, Callable[[int, int], int]] = {
    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
    "<<": operator.lshift,
    ">>": operator.rshift,
}

# the edges of the bound two tracked ints are written inside
LOW, HIGH = -(2**63), 2**63 - 1

type Case = tuple[Expression, int]


def _constants(rng: random.Random) -> tuple[dict[str, int], list[Case]]:
    """Each operation on a leaf and a constant, either way round, on seeded random ints wider
    and narrower than 64 bits, negatives among them: each leaf's value, and each term with what
    Python makes of it."""
    values: dict[str, int] = {}
    cases: list[Case] = []
    for at in range(12):
        name = f"x{at}"
        value = rng.randrange(-(2**80), 2**80) if at % 2 else rng.randrange(-300, 300)
        constant = rng.choice([1, 15, 0xFF, -8, 0, -1, rng.randrange(-(2**70), 2**70)])
        count = rng.randrange(0, 70)
        values[name] = value
        for op in ("&", "|", "^"):
            cases.append(([op, name, constant], OPERATIONS[op](value, constant)))
            cases.append(([op, constant, name], OPERATIONS[op](constant, value)))
        cases.append((["<<", name, count], value << count))
        cases.append(([">>", name, count], value >> count))
        cases.append((["~", name], ~value))
        cases.append((["&", [">>", name, 4], 15], (value >> 4) & 15))
    return values, cases


def _asked(values: dict[str, int], cases: list[Case]) -> tuple[Branch, ...]:
    """The forks that pin each leaf to its value and each term to Python's answer."""
    pins: list[Expression] = [["==", name, value] for name, value in values.items()]
    terms: list[Expression] = [["==", term, answer] for term, answer in cases]
    return tuple(fork(each, taken=True) for each in pins + terms)


@needs_cvc5
def test_cvc5_gives_each_term_with_a_constant_pythons_value() -> None:
    values, cases = _constants(random.Random(20261124))

    answer = solve(_asked(values, cases), dict.fromkeys(values, int), 30.0)

    assert isinstance(answer, Sat), answer


@needs_cvc5
@pytest.mark.parametrize("op", ["&", "|", "^"])
def test_cvc5_gives_two_tracked_ints_inside_the_bound_pythons_value(op: str) -> None:
    rng = random.Random(7)
    pairs = [(rng.randrange(LOW, HIGH), rng.randrange(LOW, HIGH)) for _ in range(4)]
    pairs += [(LOW, HIGH), (-1, LOW), (HIGH, HIGH), (0, -1)]
    values: dict[str, int] = {}
    cases: list[Case] = []
    for at, (x, y) in enumerate(pairs):
        values |= {f"x{at}": x, f"y{at}": y}
        cases.append(([op, f"x{at}", f"y{at}"], OPERATIONS[op](x, y)))

    answer = solve(_asked(values, cases), dict.fromkeys(values, int), 30.0)

    assert isinstance(answer, Sat), answer


@needs_cvc5
def test_a_wrong_value_for_a_term_with_a_constant_is_unsat() -> None:
    path = (
        fork(["==", "n", -13], taken=True),
        fork(["==", ["&", "n", 0xF0], 0xF0 & -13], taken=False),
    )

    assert isinstance(solve(path, {"n": int}, 10.0), Unsat)


# paths through bit operations, the last fork the one to take, and what Python says of an answer
PATHS: dict[str, tuple[list[tuple[Expression, bool]], dict[str, type], Callable[..., bool]]] = {
    "the ticket's probe": (
        [(["!=", ["&", "n", 1], 0], False), (["==", [">>", "n", 4], 3], True)],
        {"n": int},
        lambda n: not n & 1 and n >> 4 == 3,
    ),
    "a negative mask": (
        [(["==", ["&", "n", -16], -32], True), ([">", "n", -100], True)],
        {"n": int},
        lambda n: n & -16 == -32 and n > -100,
    ),
    "a field and a flag": (
        [(["==", ["&", [">>", "n", 8], 0xFF], 0x41], True), (["!=", ["&", "n", 0x80], 0], True)],
        {"n": int},
        lambda n: (n >> 8) & 0xFF == 0x41 and n & 0x80,
    ),
    "an inverse and a shift": (
        [(["==", ["~", ["<<", "n", 3]], -41], True)],
        {"n": int},
        lambda n: ~(n << 3) == -41,
    ),
    "two tracked ints": (
        [(["==", ["&", "x", "y"], 12], True), ([">", "x", 100], True), ([">", "y", 100], True)],
        {"x": int, "y": int},
        lambda x, y: x & y == 12 and x > 100 and y > 100,
    ),
    "an xor of two": (
        [(["==", ["^", "x", "y"], 5], True), (["<", "x", 0], True)],
        {"x": int, "y": int},
        lambda x, y: x ^ y == 5 and x < 0,
    ),
}


@needs_cvc5
@pytest.mark.parametrize("name", PATHS)
def test_cvc5_answers_a_path_through_bit_operations_as_python_takes_it(name: str) -> None:
    forks, leaves, python = PATHS[name]
    path = tuple(fork(expression, taken=taken) for expression, taken in forks)

    answer = solve(path, leaves, 10.0)

    assert isinstance(answer, Sat), answer
    assert python(*(answer.model[leaf] for leaf in leaves)), answer.model


@needs_cvc5
def test_two_tracked_ints_past_the_bound_are_unknown_rather_than_unsat() -> None:
    # Python has an answer: past the bound the term is not written, so the solver cannot say
    # there is none
    x, y = 2**70 + 5, 2**70 + 3
    path = (
        fork(["==", "x", x], taken=True),
        fork(["==", "y", y], taken=True),
        fork(["==", ["&", "x", "y"], x & y], taken=True),
    )

    assert isinstance(solve(path, {"x": int, "y": int}, 10.0), Unknown)


def test_a_constant_operand_needs_no_bound_and_two_tracked_ints_hold_one() -> None:
    constant = program((fork(["!=", ["&", "n", 6], 0], taken=True),), {"n": int})
    tracked = program((fork(["!=", ["|", "x", "y"], 0], taken=True),), {"x": int, "y": int})

    assert "(_ iand 3)" in constant.text and not constant.bounded
    assert "(_ iand 64)" in tracked.text and tracked.bounded
    assert f"(<= (- {2**63}) |arg.x| {2**63 - 1})" in tracked.text


def test_a_shift_and_an_inverse_are_written_without_iand() -> None:
    path = (fork(["==", ["~", [">>", ["<<", "n", 3], 2]], 0], taken=True),)

    text = program(path, {"n": int}).text

    assert "(* |arg.n| 8)" in text and "(div " in text and "iand" not in text


def test_a_program_that_holds_an_iand_runs_with_cvc5_s_bitwise_refinement() -> None:
    iand = program((fork(["!=", ["&", "n", 6], 0], taken=True),), {"n": int}).text
    plain = program((fork([">", "n", 6], taken=True),), {"n": int}).text

    assert "--iand-mode=bitwise" in argv(1.0, iand)
    assert "(set-option :iand-mode bitwise)" in options(1.0, iand)
    assert "--iand-mode=bitwise" not in argv(1.0, plain)
    assert not any("iand" in each for each in options(1.0, plain))
