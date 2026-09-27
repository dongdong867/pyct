"""Positions into a string in SMT-LIB: the terms positions.py writes, and cvc5 held against
Python on them, a tracked int among the positions."""

import itertools
import operator
import random
from collections.abc import Callable, Mapping

import pytest

from pyct.core.branch import Branch, Expression
from pyct.solver import strings
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.positions import (
    character,
    ends_with,
    first_index,
    last_index,
    occurrences,
    replaced,
    sliced,
    starts_with,
)
from pyct.solver.strings import encode
from tests.unit.solver.agreement import ALPHABET, PATH_LETTERS, SITE, asked, needs_cvc5
from tests.unit.solver.test_render import render


def test_plain_positions_are_the_forms_strings_writes() -> None:
    # a program with no tracked position reads as it did before positions could be tracked
    assert character("s", -1) == strings.character("s", -1)
    assert sliced("s", -2, None) == strings.sliced("s", -2, None)
    assert sliced("s", 1, 3, 1) == strings.sliced("s", 1, 3)
    assert first_index("s", '"a"') == strings.first_index("s", '"a"')
    assert last_index("s", '"a"') == strings.last_index("s", '"a"')
    assert occurrences("s", '"a"') == strings.occurrences("s", '"a"')
    assert starts_with("s", '"a"') == strings.starts_with("s", '"a"')
    assert replaced("s", '"a"', '"b"') == strings.replaced("s", '"a"', '"b"')
    assert replaced("s", '"a"', '"b"', -1) == strings.replaced("s", '"a"', '"b"')


def test_a_tracked_index_counts_back_from_the_end_when_negative() -> None:
    assert character("s", "n") == "(str.at s (ite (< n 0) (+ n (str.len s)) n))"


def test_a_reversed_string_is_cvc5s_reverse_of_the_whole() -> None:
    assert sliced("s", None, None, -1) == (
        "(let ((low! 0)) (str.rev (str.substr s low! (- (str.len s) low!))))"
    )


def test_one_replacement_is_cvc5s_first_replace_and_a_count_of_zero_is_the_string() -> None:
    assert replaced("s", '""', '"x"', 1) == '(str.replace s "" "x")'
    assert replaced("s", '"a"', '"x"', 0) == "s"


def test_a_tuple_is_any_of_its_items() -> None:
    assert starts_with("s", ('"a"', "t")) == '(or (str.prefixof "a" s) (str.prefixof t s))'
    assert ends_with("s", ('"a"',)) == '(str.suffixof "a" s)'


@pytest.mark.parametrize(
    ("form", "args"),
    [(sliced, (None, None, 2)), (replaced, ('"a"', '"b"', 2)), (character, (None,))],
    ids=["a step of two", "a count of two", "a missing index"],
)
def test_a_form_core_never_writes_is_an_error(
    form: Callable[..., str], args: tuple[object, ...]
) -> None:
    with pytest.raises(ValueError, match="pyct cannot render"):
        form("s", *args)


def test_a_tracked_position_used_twice_is_defined_once() -> None:
    text = render(
        (
            Branch(
                expression=["==", ["[:]", "s", ["+", "n", 1], None], "'a'"], taken=True, site=SITE
            ),
        ),
        {"s": str, "n": int},
    )

    # the clamp writes the position more than once, so it is named, not written out each time
    assert "(define-fun e!0 () Int (+ |arg.n| 1))" in text.splitlines()
    assert text.count("(+ |arg.n| 1)") == 1


# what a position is written as in a fixed-value case: a plain int, or a constant held to it
type Held = Callable[[int | None], int | str | None]

# each form, given a random string's value and a way to write positions, as the term it writes
# and Python's answer
type Case = tuple[Callable[[str], str], object, str]


def _positions(
    rng: random.Random, held: Held, count: int
) -> tuple[list[int | None], list[int | str | None]]:
    """Up to ``count`` random positions, some missing, as Python has them and as written."""
    values: list[int | None] = [
        rng.choice([None, *range(-7, 8)]) for _ in range(rng.randint(0, count))
    ]
    return values, [held(value) for value in values]


def _slice_case(rng: random.Random, value: str, held: Held) -> Case:
    start, stop = (rng.choice([None, *range(-7, 8)]) for _ in range(2))
    step = rng.choice([None, 1, -1])
    bounds = (held(start), held(stop))
    return (lambda s: sliced(s, *bounds, step)), value[start:stop:step], "String"


def _index_case(rng: random.Random, value: str, held: Held) -> Case:
    at = rng.randint(-len(value), len(value) - 1)
    written = held(at)
    return (lambda s: character(s, written)), value[at], "String"


SEARCHES: dict[str, tuple[Callable[..., str], Callable[..., object], str]] = {
    "find": (first_index, str.find, "Int"),
    "rfind": (last_index, str.rfind, "Int"),
    "count": (occurrences, str.count, "Int"),
    "startswith": (starts_with, str.startswith, "Bool"),
    "endswith": (ends_with, str.endswith, "Bool"),
}


def _search_case(rng: random.Random, value: str, held: Held) -> Case:
    head = rng.choice(list(SEARCHES))
    form, meant, sort = SEARCHES[head]
    sub = value[rng.randint(0, len(value)) :][: rng.randint(0, 2)] if rng.random() < 0.5 else ""
    sub = sub or "".join(rng.choices(ALPHABET, k=rng.randint(0, 2)))
    needle: object = sub
    written: object = encode(sub)
    if head in ("startswith", "endswith") and rng.random() < 0.4:
        needle = (sub, rng.choice(ALPHABET))
        written = tuple(encode(item) for item in needle)
    places, place_terms = _positions(rng, held, 2)
    return (lambda s: form(s, written, *place_terms)), meant(value, needle, *places), sort


def _replace_case(rng: random.Random, value: str, held: Held) -> Case:
    count = rng.choice([1, 0, -1])
    old = "".join(rng.choices(ALPHABET, k=rng.randint(0 if count >= 0 else 1, 2)))
    if value and rng.random() < 0.5:
        old = value[rng.randint(0, len(value) - 1) :][: rng.randint(1, 2)]
    new = "".join(rng.choices(ALPHABET, k=rng.randint(0, 2)))
    answer = value.replace(old, new, count)
    return (lambda s: replaced(s, encode(old), encode(new), count)), answer, "String"


MAKERS = [_index_case, _slice_case, _search_case, _replace_case]


def _program(count: int) -> tuple[list[str], list[object]]:
    """One program asking the answer of every case, and Python's answers, fixed by the seed.

    Each string is a constant held to its value, as a tracked parameter
    reaches a form, and each position is a plain int or, half the time, an
    Int constant held to it, as a tracked int does.
    """
    rng = random.Random(0)
    lines = ["(set-logic ALL)"]
    python: list[object] = []
    for at in range(count):
        maker = MAKERS[at % len(MAKERS)]
        value = "".join(rng.choices(ALPHABET, k=rng.randint(1 if maker is _index_case else 0, 5)))
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        term, answer, sort = maker(rng, value, _holder(rng, lines, at))
        lines += [f"(declare-const v{at} {sort})", f"(assert (= v{at} {term(f's{at}')}))"]
        python.append(answer)
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(count))}))"]
    return lines, python


def _holder(rng: random.Random, lines: list[str], at: int) -> Held:
    """How case ``at`` writes a position: as it is, or half the time a constant held to it."""
    tracked = rng.random() < 0.5
    made: list[int] = []

    def held(value: int | None) -> int | str | None:
        if value is None or not tracked:
            return value
        name = f"n{at}_{len(made)}"
        made.append(value)
        number = str(value) if value >= 0 else f"(- {-value})"
        lines.extend([f"(declare-const {name} Int)", f"(assert (= {name} {number}))"])
        return name

    return held


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_position() -> None:
    lines, python = _program(800)

    answers = asked(lines)

    # every value is fixed, so cvc5 only works each term out: this holds the terms to Python
    assert len(answers) == len(python)
    disagreements = [
        (at, said, meant)
        for at, (said, meant) in enumerate(zip(answers, python, strict=True))
        if said != meant
    ]
    assert disagreements == []


def _minus(*operands: int) -> int:
    return -operands[0] if len(operands) == 1 else operands[0] - operands[1]


# what each head on a position path means in Python
PYTHON_HEADS: dict[str, Callable[..., object]] = {
    "[]": lambda s, i: s[i],
    "[:]": lambda s, i, j, *step: s[i : j : (step or [None])[0]],
    "()": lambda *items: items,
    "len": len,
    "+": operator.add,
    "-": _minus,
    "find": lambda s, *args: s.find(*args),
    "rfind": lambda s, *args: s.rfind(*args),
    "index": lambda s, *args: s.index(*args),
    "count": lambda s, *args: s.count(*args),
    "startswith": lambda s, *args: s.startswith(*args),
    "endswith": lambda s, *args: s.endswith(*args),
    "replace": lambda s, *args: s.replace(*args),
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    ">=": operator.ge,
}


def _python(expression: Expression, leaves: Mapping[str, object]) -> object:
    """What Python makes of a condition, each leaf by its value and a literal as it reads."""
    if isinstance(expression, list):
        head, *operands = expression
        return PYTHON_HEADS[str(head)](*(_python(part, leaves) for part in operands))
    if isinstance(expression, str):
        return leaves[expression] if expression in leaves else eval(expression)  # noqa: S307
    return expression


def _position(rng: random.Random) -> Expression:
    """A random position: missing, plain, or tracked."""
    positions: list[Expression] = [None, rng.randint(-3, 3), "n", ["-", "n"], ["+", "n", 1]]
    return rng.choice(positions)


def _string(rng: random.Random) -> str:
    return repr("".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 2))))


def _guards(index: Expression) -> list[Expression]:
    """The forks a tracked index records before it reads, in order."""
    return [[">", ["len", "s"], index], [">=", ["len", "s"], ["-", index]]]


def _index_fork(rng: random.Random) -> tuple[Expression, list[Expression]]:
    indexes: list[Expression] = ["n", ["+", "n", 1], ["-", "n"]]
    index = rng.choice(indexes)
    return ["==", ["[]", "s", index], repr(rng.choice(PATH_LETTERS))], _guards(index)


def _slice_fork(rng: random.Random) -> tuple[Expression, list[Expression]]:
    steps: list[list[Expression]] = [[], [1], [-1]]
    bounds = [_position(rng), _position(rng), *rng.choice(steps)]
    return ["==", ["[:]", "s", *bounds], _string(rng)], []


def _search_fork(rng: random.Random) -> tuple[Expression, list[Expression]]:
    end: list[Expression] = [_position(rng)] if rng.random() < 0.5 else []
    search: Expression = [rng.choice(["find", "rfind", "count"]), "s", _string(rng), "n", *end]
    return [rng.choice(["==", "<", ">="]), search, rng.randint(-1, 3)], []


def _prefix_fork(rng: random.Random) -> tuple[Expression, list[Expression]]:
    needles: list[Expression] = [_string(rng), ["()", _string(rng), _string(rng)]]
    head = rng.choice(["startswith", "endswith"])
    return [head, "s", rng.choice(needles), _position(rng)], []


def _replace_fork(rng: random.Random) -> tuple[Expression, list[Expression]]:
    replace: Expression = ["replace", "s", _string(rng), _string(rng), rng.choice([0, 1])]
    return ["==", ["[:]", replace, None, "n"], _string(rng)], []


# each kind of random fork on a position, and the forks it records before it, in order
FORKS = [_index_fork, _slice_fork, _search_fork, _prefix_fork, _replace_fork]


def _flipped_path(rng: random.Random) -> tuple[Branch, ...]:
    """The forks some input takes through random position forks, the last one flipped."""
    leaves: dict[str, object] = {
        "s": "".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 5))),
        "n": rng.randint(-4, 4),
    }
    forks: list[Branch] = []
    for _ in range(rng.randint(1, 4)):
        condition, guards = rng.choice(FORKS)(rng)
        forks += _taken([*guards, condition], leaves)
        if forks[-1].expression is not condition:
            break
    last = forks[-1]
    return (*forks[:-1], Branch(expression=last.expression, taken=not last.taken, site=SITE))


def _taken(parts: list[Expression], leaves: Mapping[str, object]) -> list[Branch]:
    """The forks the input takes through the parts, up to the first guard it does not take:
    past that, the index raises."""
    forks = []
    for part in parts:
        forks.append(Branch(expression=part, taken=bool(_python(part, leaves)), site=SITE))
        if not forks[-1].taken and part is not parts[-1]:
            break
    return forks


def _takes(path: tuple[Branch, ...], leaves: Mapping[str, object]) -> bool:
    """Whether the input takes every fork of the path the way the plan says."""
    try:
        return all(bool(_python(fork.expression, leaves)) == fork.taken for fork in path)
    except IndexError:
        return False


def _witness(path: tuple[Branch, ...]) -> bool:
    """Whether some short string and small n take the path: an unsat must have none."""
    texts = ["".join(p) for k in range(4) for p in itertools.product("abz", repeat=k)]
    return any(_takes(path, {"s": s, "n": n}) for s in texts for n in range(-5, 6))


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_position_path_it_answers() -> None:
    rng = random.Random(0)
    paths = [_flipped_path(rng) for _ in range(60)]

    answers = [solve(path, {"s": str, "n": int}, 2.0) for path in paths]

    # an error is cvc5 failing to answer at all, which is never agreement
    assert [answer for answer in answers if isinstance(answer, Error)] == []
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if (isinstance(answer, Sat) and not _takes(path, answer.model))
        or (isinstance(answer, Unsat) and _witness(path))
    ]
    assert wrong == []
    # most paths are answered, so a clean result is not an empty one
    assert sum(isinstance(answer, Sat) for answer in answers) > len(paths) // 2
