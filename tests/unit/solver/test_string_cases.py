"""The case changes, strips and paddings in SMT-LIB, and cvc5 held against Python on them."""

import random
from collections.abc import Callable

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cases import CASES, PADDINGS
from pyct.solver.cvc5 import solve
from pyct.solver.recased import HEAD, TO_DECLARE
from pyct.solver.strings import encode
from tests.unit.solver.agreement import (
    SITE,
    ascii_disagrees,
    asked,
    flipped_path,
    method,
    needs_cvc5,
)
from tests.unit.solver.test_render import render

# the characters random strings are made of: letters of both cases, the characters a strip or
# a padding here meets, a sign for zfill, and every ASCII character now and then
COMMON = list("aAzZ09 \t_-+*")
ASCII = [chr(code) for code in range(128)]

# a case: the term to ask of the string in a constant, and Python's answer
type Case = tuple[Callable[[str], str], str]


def _value(rng: random.Random, longest: int) -> str:
    pool = COMMON if rng.random() < 0.7 else ASCII
    return "".join(rng.choices(pool, k=rng.randint(0, longest)))


def _case_change(rng: random.Random, value: str) -> Case:
    head = rng.choice(list(CASES))
    if head.endswith("strip") and rng.random() < 0.5:
        characters = _value(rng, 3)
        return (lambda s: CASES[head](s, encode(characters))), getattr(value, head)(characters)
    return (lambda s: CASES[head](s)), getattr(value, head)()


def _padding(rng: random.Random, value: str) -> Case:
    head = rng.choice(list(PADDINGS))
    width = rng.randint(-2, 9)
    if head == "zfill" or rng.random() < 0.5:
        return (lambda s: PADDINGS[head](s, width)), getattr(value, head)(width)
    fill = rng.choice("*0 é")
    return (lambda s: PADDINGS[head](s, width, fill)), getattr(value, head)(width, fill)


def _program(cases: list[tuple[str, Case]]) -> list[str]:
    """One program asking every case's term of its value, held in a constant."""
    lines = ["(set-logic ALL)"]
    for at, (value, (term, _)) in enumerate(cases):
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        lines += [f"(declare-const v{at} String)", f"(assert (= v{at} {term(f's{at}')}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]
    return lines


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_case_change_strip_and_padding() -> None:
    rng = random.Random(0)
    values = [_value(rng, 6) for _ in range(600)]
    cases = [
        (value, (_case_change if at % 2 else _padding)(rng, value))
        for at, value in enumerate(values)
    ]

    answers = asked(_program(cases))

    assert answers == [answer for _, (_, answer) in cases]


def _declared_program(values: list[tuple[str, str]]) -> list[str]:
    """One program asking title or swapcase of each value, each rest declared by name."""
    lines = ["(set-logic ALL)"]
    for at, (head, value) in enumerate(values):
        _, term, condition = TO_DECLARE[head](f"d{at}", f"s{at}")
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        lines += [f"(declare-const d{at} String)", f"(assert {condition})"]
        lines += [f"(declare-const v{at} String)", f"(assert (= v{at} {term}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(values)))}))"]
    return lines


@needs_cvc5
def test_cvc5_agrees_with_python_on_title_and_swapcase() -> None:
    rng = random.Random(0)
    # most within the characters written one by one, and some past them into the declared rest
    values = [
        (rng.choice(list(TO_DECLARE)), _value(rng, HEAD if at % 4 else HEAD + 6))
        for at in range(120)
    ]

    answers = asked(_declared_program(values))

    assert answers == [getattr(value, head)() for head, value in values]


def test_a_declared_string_is_named_in_its_value_and_held_by_its_condition() -> None:
    text = render(
        (Branch(expression=["==", ["title", "s"], "'Ab'"], taken=True, site=SITE),), {"s": str}
    )

    lines = text.splitlines()
    assert "(declare-const e!0 String)" in lines
    # the condition says what the rest is, and the fork's own assertion reads the value
    assert lines[lines.index("(declare-const e!0 String)") + 1].startswith("(assert (and ")
    assert lines[-3].startswith("(assert (= (str.++ (str.++ ") and "e!0)" in lines[-3]


# what each head on a case path means in Python
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    **{head: method(head) for head in [*CASES, *PADDINGS, *TO_DECLARE]},
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
}

# the letters of a random path's strings and literals
LETTERS: list[str] = list("aAb -")


def _term(rng: random.Random, receiver: Expression) -> Expression:
    """One random case change, strip or padding of the receiver."""
    head = rng.choice([*CASES, *PADDINGS, *TO_DECLARE])
    if head in PADDINGS:
        fill = [] if head == "zfill" or rng.random() < 0.5 else [repr(rng.choice("*-"))]
        return [head, receiver, rng.randint(0, 5), *fill]
    if head.endswith("strip") and rng.random() < 0.5:
        return [head, receiver, repr(rng.choice(["a", " ", "-a"]))]
    return [head, receiver]


def _compared(rng: random.Random) -> tuple[Expression, Expression | None]:
    """A random change of s, a third of the time of another, compared with a literal."""
    term = _term(rng, "s")
    if rng.random() < 0.3:
        term = _term(rng, term)
    literal = repr("".join(rng.choices(LETTERS, k=rng.randint(0, 3))))
    return [rng.choice(["==", "!=", "<"]), term, literal], None


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_case_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [
        flipped_path(
            "".join(rng.choices(LETTERS, k=rng.randint(0, 5))),
            [_compared(rng) for _ in range(rng.randint(1, 3))],
            PYTHON_HEADS,
        )
        for _ in range(60)
    ]

    answers = [solve(path, {"s": str}, 2.0) for path in paths]

    assert [answer for answer in answers if isinstance(answer, Error)] == []
    answered = [
        path for path, answer in zip(paths, answers, strict=True) if isinstance(answer, Sat | Unsat)
    ]
    heads = {str(part) for path in answered for fork in path for part in _heads(fork.expression)}
    assert heads >= {*CASES, *PADDINGS, *TO_DECLARE}
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if ascii_disagrees(path, answer, PYTHON_HEADS, LETTERS, 3)
    ]
    assert wrong == []


def _heads(expression: Expression) -> list[Expression]:
    """Every head an expression holds, its own and its parts'."""
    if not isinstance(expression, list):
        return []
    return [expression[0], *(head for part in expression[1:] for head in _heads(part))]
