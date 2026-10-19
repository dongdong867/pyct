"""A split built by steps in SMT-LIB: the edges of a word, and cvc5 held against Python on the
forks core records for each step (split-a-string-cut-at-a-tracked-position)."""

import random
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.branch import Branch, Expression, SinkItem
from pyct.core.str_steps import last_word, next_word, word_end, word_start
from pyct.core.strs import ConcolicStr
from pyct.solver.answer import Error, Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.splits import named_classes
from pyct.solver.strings import encode
from pyct.solver.words import WORD_EDGES
from tests.unit.solver.agreement import SITE, asked, disagrees, method, needs_cvc5
from tests.unit.solver.test_render import render

# the characters the edges are read on: whitespace in and past ASCII, and letters
_SPACED = list("ab \t\n\x0b\x1c\x1f\x85\xa0    　​")

# what each edge means in Python, the position past the end where one is missing
_EDGES: dict[str, Callable[..., int]] = {
    "nextword": next_word,
    "wordend": word_end,
    "lastword": lambda text, end=None: last_word(text, len(text) if end is None else end),
    "wordstart": word_start,
}


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_edge_of_a_word() -> None:
    rng = random.Random(0)
    lines, python = ["(set-logic ALL)"], []
    for at in range(400):
        text = "".join(rng.choices(_SPACED, k=rng.randint(0, 7)))
        head = rng.choice(list(WORD_EDGES))
        position = rng.randint(0, len(text))
        operands: tuple[Any, ...] = () if head == "lastword" and rng.random() < 0.3 else (position,)
        term = WORD_EDGES[head](f"s{at}", *operands)
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(text)}))"]
        lines += [f"(declare-const v{at} Int)", f"(assert (= v{at} {term}))"]
        python.append(_EDGES[head](text, *operands))
    lines[1:1] = named_classes("\n".join(lines))
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(python)))}))"]

    assert asked(lines) == python


def test_an_edge_from_a_negative_position_is_an_error() -> None:
    with pytest.raises(ValueError, match="0 or more"):
        WORD_EDGES["nextword"]("s", -1)


# the letters a path's string is made of: a separator, whitespace, a letter and the mark a
# cut starts at
_LETTERS: list[str] = list("a, #")

# what each head a step's fork holds means in Python
_HEADS: dict[str, Callable[..., object]] = {
    "find": method("find"),
    "rfind": method("rfind"),
    "[:]": lambda s, start, stop: s[start:stop],
    "+": lambda a, b: a + b,
    "len": len,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    **_EDGES,
}

# each split built by steps, on one leaf: the string cut where its mark is, a separator taken
# from its first character, and a limit at the mark's place
_SPLITS: list[Callable[[Any], object]] = [
    lambda s: s[s.find("#") :].split(","),
    lambda s: s[s.find("#") :].rsplit(","),
    lambda s: s[s.find("#") :].split(),
    lambda s: s[s.find("#") :].rsplit(None, 1),
    lambda s: s[1:].split(s[:1]),
    lambda s: s[1:].rsplit(s[:1], 1),
    lambda s: s.split(",", s.find("#")),
    lambda s: s.rsplit(None, s.find("#")),
]


def _flipped(s: str, split: Callable[[Any], object], rng: random.Random) -> tuple[Branch, ...]:
    """The forks the split records on s, cut after one picked at random, which is flipped."""
    sink: list[SinkItem] = []
    split(ConcolicStr.made(s, expression="s", sink=sink))
    forks = [item for item in sink if isinstance(item, Branch)]
    last = rng.randrange(len(forks))
    flipped = Branch(forks[last].expression, not forks[last].taken, SITE)
    return (*(Branch(fork.expression, fork.taken, SITE) for fork in forks[:last]), flipped)


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_step_it_flips() -> None:
    rng = random.Random(0)
    paths = []
    for _ in range(80):
        s = "".join(rng.choices(_LETTERS, k=rng.randint(1, 6)))
        paths.append(_flipped(s, rng.choice(_SPLITS), rng))

    answers = [solve(path, {"s": str}, 5.0) for path in paths]

    assert [answer for answer in answers if isinstance(answer, Error)] == []
    assert all(isinstance(answer, Sat | Unsat) for answer in answers), answers
    wrong = [
        path
        for path, answer in zip(paths, answers, strict=True)
        if disagrees(path, answer, _HEADS, _LETTERS, 4)
    ]
    assert wrong == []


@pytest.mark.parametrize(
    "piece",
    [
        ["[:]", "s", None, ["find", "s", "'@'"]],
        ["[:]", "s", ["+", ["rfind", "s", "'@'"], 1], None],
        ["[:]", "s", ["nextword", "s", 0], ["wordend", "s", ["nextword", "s", 0]]],
    ],
    ids=["before a search's answer", "past a search back", "between a word's edges"],
)
def test_a_count_beside_a_piece_a_step_cut_is_written_as_the_string_stands(piece: Any) -> None:
    count: Expression = ["!=", ["count", "s", "'@'"], 1]
    alone = render((Branch(count, False, SITE),), {"s": str})
    beside = render(
        (Branch(["==", piece, "'a'"], True, SITE), Branch(count, False, SITE)), {"s": str}
    )

    # the count reads the string reversed alone, and as it stands beside a piece cut at a step,
    # as beside a split's own pieces
    reversed_count, as_written = (
        '(str.replace_all (str.rev |arg.s|) "@" "")',
        '(str.replace_all |arg.s| "@" "")',
    )
    assert reversed_count in alone and as_written not in alone
    assert as_written in beside and reversed_count not in beside
