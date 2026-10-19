"""A split built by steps in core (split-a-string-cut-at-a-tracked-position): Python's own list,
each piece a tracked slice of the string, and one fork a step, each taking the side Python's own
evaluation of its condition takes."""

import ast
import random
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, Fact, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.str_steps import last_word, next_word, word_end, word_start
from pyct.core.strs import ConcolicStr

# what each head a step's fork, a piece or a receiver holds means in Python
_HEADS: Mapping[str, Callable[..., object]] = {
    "find": lambda s, sub, *at: s.find(sub, *at),
    "rfind": lambda s, sub, *at: s.rfind(sub, *at),
    "split": lambda s, *operands: s.split(*operands),
    "[:]": lambda s, start, stop: s[start:stop],
    "[]": lambda items, at: items[at],
    "pin": lambda at, operand, value: at if value is None or operand == value else None,
    "+": lambda a, b: a + b,
    "-": lambda a, b=None: -a if b is None else a - b,
    "%": lambda a, b: a % b,
    "len": len,
    "str": str,
    "int": int,
    "!=": lambda a, b: a != b,
    "==": lambda a, b: a == b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "nextword": next_word,
    "wordend": word_end,
    "lastword": lambda s, end=None: last_word(s, len(s) if end is None else end),
    "wordstart": word_start,
}


def evaluate(expression: Expression, args: Mapping[str, object]) -> object:
    """What Python makes of a form over the arguments: a name is an argument, a quoted text a
    literal, and a list an operation."""
    if isinstance(expression, list):
        head, *operands = expression
        assert isinstance(head, str)
        return _HEADS[head](*(evaluate(operand, args) for operand in operands))
    if isinstance(expression, str):
        return ast.literal_eval(expression) if expression[:1] in "'\"" else args[expression]
    return expression


def forks(sink: list[SinkItem]) -> list[Branch]:
    return [item for item in sink if isinstance(item, Branch)]


def agrees(sink: list[SinkItem], pieces: list[Any], args: Mapping[str, object]) -> None:
    """Every fork and fact takes Python's side, and every piece is what its form says."""
    for item in sink:
        assert not isinstance(item, Downgrade), item
        if isinstance(item, Branch | Fact) and item.expression is not None:
            assert bool(evaluate(item.expression, args)) is item.taken, item
    for part in pieces:
        assert evaluate(part.expression, args) == str.__str__(part), part.expression


def _tracked(args: Mapping[str, object], sink: list[SinkItem]) -> dict[str, Any]:
    """Each argument tracked by its name: a str, an int or a bool."""
    made: dict[str, Any] = {}
    for name, value in args.items():
        if isinstance(value, bool):
            made[name] = ConcolicBool.made(value, expression=name, sink=sink)
        elif isinstance(value, int):
            made[name] = ConcolicInt.made(value, expression=name, sink=sink)
        else:
            assert isinstance(value, str)
            made[name] = ConcolicStr.made(value, expression=name, sink=sink)
    return made


# the strings a split is built of: separators, whitespace past ASCII among them, and letters
_LETTERS = list("ab,;  \t\n\x1c\u3000\u2028\xa0")

# each receiver a split here cannot be written as one formula on, by the arguments it reads
_RECEIVERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "a cut at a tracked bound": lambda a: a["s"][a["i"] :],
    "an int's text": lambda a: str(a["n"]),
    "a join with an int's text": lambda a: a["s"] + str(a["n"]),
    "a piece at a tracked index": lambda a: a["s"].split(";")[a["i"] % 2 - 1],
    "a plain string": lambda a: a["s"],
}

# each split, by the operands it is handed
_SPLITS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {
    "split by a separator": lambda r, a: r.split(","),
    "split by a tracked separator": lambda r, a: r.split(a["d"]),
    "split by a tracked limit": lambda r, a: r.split(",", a["k"]),
    "split by a tracked bool limit": lambda r, a: r.split(",", a["b"]),
    "split by whitespace": lambda r, a: r.split(),
    "split by whitespace to a tracked limit": lambda r, a: r.split(None, a["k"]),
    "rsplit by a separator": lambda r, a: r.rsplit(","),
    "rsplit by a tracked separator to a tracked limit": lambda r, a: r.rsplit(a["d"], a["k"]),
    "rsplit by whitespace": lambda r, a: r.rsplit(),
    "rsplit by whitespace to a tracked limit": lambda r, a: r.rsplit(None, a["k"]),
}


def _seed(rng: random.Random) -> dict[str, object]:
    return {
        "s": "".join(rng.choices(_LETTERS, k=rng.randint(0, 9))),
        "i": rng.randint(-3, 4),
        "n": rng.choice([0, 5, 100, 1010, -20, 30303]),
        "d": rng.choice([",", ";", "a", "aa", " ", "\u3000"]),
        "k": rng.randint(-2, 3),
        "b": rng.choice([True, False]),
    }


@pytest.mark.parametrize("receiver", _RECEIVERS)
@pytest.mark.parametrize("split", _SPLITS)
def test_each_step_takes_python_s_side(receiver: str, split: str) -> None:
    rng = random.Random(f"{receiver} {split}")
    for _ in range(12):
        args = _seed(rng)
        sink: list[SinkItem] = []
        tracked = _tracked(args, sink)
        made = _RECEIVERS[receiver](tracked)
        if not isinstance(made, ConcolicStr):
            continue
        plain = _SPLITS[split](str.__str__(made), args)

        pieces = _SPLITS[split](made, tracked)

        if type(pieces) is not list:
            # a split of the string itself by plain operands is the one formula of origin/v2
            assert receiver == "a plain string" and "tracked" not in split, split
            continue
        assert [str.__str__(part) for part in pieces] == plain, (args, pieces, plain)
        agrees(sink, pieces, args)
        # one fork a piece, and a few more: the limit's, the separator's and the last search
        assert len(forks(sink)) <= 2 * len(pieces) + 4, forks(sink)


def test_a_cut_split_forks_once_a_separator() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("xa,b", expression="s", sink=sink)
    i = ConcolicInt.made(1, expression="i", sink=sink)

    pieces = s[i:].split(",")

    cut: Expression = ["[:]", "s", "i", None]
    first: Expression = ["find", cut, "','"]
    second: Expression = ["find", cut, "','", ["+", first, 1]]
    assert [(fork.expression, fork.taken) for fork in forks(sink)] == [
        (["!=", first, -1], True),
        (["!=", second, -1], False),
    ]
    assert [part.expression for part in pieces] == [
        ["[:]", cut, None, first],
        ["[:]", cut, ["+", first, 1], None],
    ]


def test_a_tracked_separator_s_cut_forks_on_its_search() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b", expression="s", sink=sink)
    d = ConcolicStr.made(",", expression="d", sink=sink)

    s.split(d)

    first: Expression = ["find", "s", "d"]
    second: Expression = ["find", "s", "d", ["+", first, ["len", "d"]]]
    assert [(fork.expression, fork.taken) for fork in forks(sink)] == [
        (["!=", "d", "''"], True),
        (["!=", first, -1], True),
        (["!=", second, -1], False),
    ]


def test_a_tracked_limit_forks_before_each_cut() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b,c", expression="s", sink=sink)
    n = ConcolicInt.made(1, expression="n", sink=sink)

    pieces = s.split(",", n)

    assert [str.__str__(part) for part in pieces] == ["a", "b,c"]
    assert [(fork.expression, fork.taken) for fork in forks(sink)] == [
        (["<", "n", 0], False),
        ([">", "n", 0], True),
        (["!=", ["find", "s", "','"], -1], True),
        ([">", "n", 1], False),
    ]


def test_a_tracked_bool_limit_is_never_negative() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b", expression="s", sink=sink)
    b = ConcolicBool.made(True, expression="b", sink=sink)

    assert [str.__str__(part) for part in s.split(",", b)] == ["a", "b"]
    assert forks(sink)[0].expression == [">", ["int", "b"], 0]


def test_an_empty_tracked_separator_forks_then_raises_python_s_error() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b", expression="s", sink=sink)
    d = ConcolicStr.made("", expression="d", sink=sink)
    text: str = "a,b"
    with pytest.raises(ValueError) as python:
        text.split("")

    with pytest.raises(ValueError) as raised:
        s.split(d)

    assert str(raised.value) == str(python.value)
    assert [(fork.expression, fork.taken) for fork in forks(sink)] == [(["!=", "d", "''"], False)]


@pytest.mark.parametrize("limit", ["1", 1.5, None, [1]])
def test_a_limit_python_refuses_raises_python_s_error(limit: Any) -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b", expression="s", sink=sink)
    i = ConcolicInt.made(0, expression="i", sink=sink)
    text: str = "a,b"
    with pytest.raises(TypeError) as python:
        text.split(",", limit)

    with pytest.raises(TypeError) as raised:
        s[i:].split(",", limit)

    assert str(raised.value) == str(python.value)
    assert not forks(sink), sink


def test_a_whitespace_rsplit_keeps_the_whitespace_before_its_first_piece() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made(" a\u3000b  c ", expression="s", sink=sink)
    i = ConcolicInt.made(0, expression="i", sink=sink)

    pieces = s[i:].rsplit(None, 1)

    assert [str.__str__(part) for part in pieces] == [" a\u3000b", "c"]
    agrees(sink, pieces, {"s": " a\u3000b  c ", "i": 0})


def test_an_overlapping_separator_rsplits_as_python() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("aaa", expression="s", sink=sink)
    d = ConcolicStr.made("aa", expression="d", sink=sink)

    pieces = s.rsplit(d)

    assert [str.__str__(part) for part in pieces] == ["a", ""]
    agrees(sink, pieces, {"s": "aaa", "d": "aa"})


def test_a_plain_split_of_a_string_the_solver_works_out_is_one_formula() -> None:
    sink: list[SinkItem] = []
    s: Any = ConcolicStr.made("a,b", expression="s", sink=sink)

    pieces = s.split(",")

    assert type(pieces) is not list and not sink
    assert getattr(pieces, "expression", None) == ["split", "s", "','"]


@pytest.mark.parametrize(
    ("edge", "text", "at", "expected"),
    [
        (next_word, " \t\u3000a b", 0, 3),
        (next_word, "a  ", 1, -1),
        (word_end, "ab\x1cc", 0, 2),
        (word_end, "abc", 1, 3),
        (last_word, "a b\u2028 ", 5, 2),
        (last_word, "   ", 3, -1),
        (word_start, "a b\xa0cd", 6, 4),
        (word_start, "abc", 3, 0),
    ],
)
def test_a_word_s_edges_read_python_s_whitespace(
    edge: Callable[[str, int], int], text: str, at: int, expected: int
) -> None:
    assert edge(text, at) == expected
