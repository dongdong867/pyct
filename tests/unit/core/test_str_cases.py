"""The character checks, case changes, strips, paddings and splits a ConcolicStr teaches: what
each hands back, the expression it carries, and the forms left to str as a downgrade."""

from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, Expression, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.str_operands import plain
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

# a character past the last one cvc5 holds
PAST_CVC5 = "\U00030000"

CHECKS = [
    "isdigit",
    "isdecimal",
    "isnumeric",
    "isalpha",
    "isalnum",
    "isspace",
    "isupper",
    "islower",
    "isascii",
    "isprintable",
    "istitle",
    "isidentifier",
]


def _tracked(value: str, sink: list[SinkItem] | None = None) -> ConcolicStr:
    return ConcolicStr(value, expression="s", sink=[] if sink is None else sink)


@pytest.mark.parametrize("name", CHECKS)
@pytest.mark.parametrize("value", ["", "Ab1", " ", "ABC", "x_1", "²"])
def test_a_check_is_strs_own_answer_as_a_tracked_bool(name: str, value: str) -> None:
    sink: list[SinkItem] = []

    answer = getattr(_tracked(value, sink), name)()

    assert isinstance(answer, ConcolicBool)
    assert int.__bool__(answer) is getattr(value, name)()
    assert answer.expression == [name, "s"]
    # nothing is recorded until the target tests the answer
    assert sink == []


# each case change, strip and padding on s = " aB-c ": the call, and the expression it carries
CHANGES: dict[str, tuple[Callable[[str], object], Expression]] = {
    "s.upper()": (lambda s: s.upper(), ["upper", "s"]),
    "s.lower()": (lambda s: s.lower(), ["lower", "s"]),
    "s.capitalize()": (lambda s: s.capitalize(), ["capitalize", "s"]),
    "s.title()": (lambda s: s.title(), ["title", "s"]),
    "s.swapcase()": (lambda s: s.swapcase(), ["swapcase", "s"]),
    "s.casefold()": (lambda s: s.casefold(), ["casefold", "s"]),
    "s.strip()": (lambda s: s.strip(), ["strip", "s"]),
    "s.strip(None)": (lambda s: s.strip(None), ["strip", "s"]),
    "s.lstrip(' a')": (lambda s: s.lstrip(" a"), ["lstrip", "s", "' a'"]),
    "s.rstrip()": (lambda s: s.rstrip(), ["rstrip", "s"]),
    "s.zfill(9)": (lambda s: s.zfill(9), ["zfill", "s", 9]),
    "s.center(9)": (lambda s: s.center(9), ["center", "s", 9]),
    "s.center(9, '*')": (lambda s: s.center(9, "*"), ["center", "s", 9, "'*'"]),
    "s.ljust(True, '*')": (lambda s: s.ljust(True, "*"), ["ljust", "s", 1, "'*'"]),
    "s.rjust(8)": (lambda s: s.rjust(8), ["rjust", "s", 8]),
}


@pytest.mark.parametrize(("call", "expression"), CHANGES.values(), ids=list(CHANGES))
def test_a_change_is_strs_own_answer_as_a_tracked_str(
    call: Callable[[str], object], expression: Expression
) -> None:
    sink: list[SinkItem] = []

    changed = call(_tracked(" aB-c ", sink))

    assert isinstance(changed, ConcolicStr)
    assert str.__str__(changed) == call(" aB-c ")
    assert changed.expression == expression
    assert sink == []


# each split of s = "a,b c": the call, and the split every piece of it names
SPLITS: dict[str, tuple[Callable[[str], object], Expression]] = {
    "s.split()": (lambda s: s.split(), ["split", "s"]),
    "s.split(None, 1)": (lambda s: s.split(None, 1), ["split", "s", None, 1]),
    "s.split(',')": (lambda s: s.split(","), ["split", "s", "','"]),
    "s.rsplit(' ', 0)": (lambda s: s.rsplit(" ", 0), ["rsplit", "s", "' '", 0]),
    "s.rsplit(',')": (lambda s: s.rsplit(","), ["rsplit", "s", "','"]),
    "s.rsplit('aa', 1)": (lambda s: s.rsplit("aa", 1), ["rsplit", "s", "'aa'", 1]),
    "s.partition(',')": (lambda s: s.partition(","), ["partition", "s", "','"]),
    "s.partition('x')": (lambda s: s.partition("x"), ["partition", "s", "'x'"]),
    "s.splitlines()": (lambda s: s.splitlines(), ["splitlines", "s"]),
    "s.splitlines(True)": (lambda s: s.splitlines(True), ["splitlines", "s", True]),
}


@pytest.mark.parametrize(("call", "whole"), SPLITS.values(), ids=list(SPLITS))
def test_a_split_hands_back_strs_own_pieces_each_tracked_at_its_position(
    call: Callable[[str], object], whole: Expression
) -> None:
    sink: list[SinkItem] = []

    parts = call(_tracked("a,b c", sink))

    plain = call("a,b c")
    assert isinstance(parts, list | tuple) and isinstance(plain, list | tuple)
    assert type(parts) is type(plain)
    assert all(isinstance(part, ConcolicStr) for part in parts)
    assert [str.__str__(part) for part in parts] == list(plain)
    assert [part.expression for part in parts] == [["[]", whole, at] for at in range(len(plain))]
    # partition asks a str subclass for its text where the separator is missing; that call is
    # pyct's, on the plain value, so it is not the target's downgrade
    assert sink == []


def test_every_piece_of_a_split_holds_the_one_split() -> None:
    parts = _tracked("a b c").split()

    # one list for all, so a program reads the split once however many pieces the target takes
    assert isinstance(parts, list)
    expressions = [part.expression for part in parts if isinstance(part, ConcolicStr)]
    wholes = [expression[1] for expression in expressions if isinstance(expression, list)]
    assert len(wholes) == 3
    assert all(whole is wholes[0] for whole in wholes)


# each form of a taught method pyct does not encode: the call, and the name its downgrade carries
NOT_ENCODED: dict[str, tuple[Callable[[str], object], str]] = {
    "s.strip(tracked)": (lambda s: s.strip(_tracked("a")), "strip"),
    "s.strip(past cvc5)": (lambda s: s.strip(PAST_CVC5), "strip"),
    "s.center(9, tracked)": (lambda s: s.center(9, _tracked("*")), "center"),
    "s.ljust(tracked int)": (lambda s: s.ljust(ConcolicInt(9, expression="n", sink=[])), "ljust"),
    "s.split(sep=',')": (lambda s: s.split(sep=","), "split"),
    "s.split(tracked)": (lambda s: s.split(_tracked(",")), "split"),
    "s.split(past cvc5)": (lambda s: s.split(PAST_CVC5), "split"),
    "s.rsplit('aa')": (lambda s: s.rsplit("aa"), "rsplit"),
    "s.rsplit('aba', -1)": (lambda s: s.rsplit("aba", -1), "rsplit"),
    "s.partition(tracked)": (lambda s: s.partition(_tracked(",")), "partition"),
    "s.splitlines(keepends=True)": (lambda s: s.splitlines(keepends=True), "splitlines"),
}


@pytest.mark.parametrize(("call", "name"), NOT_ENCODED.values(), ids=list(NOT_ENCODED))
def test_a_form_pyct_does_not_encode_is_strs_own_and_a_downgrade(
    call: Callable[[str], object], name: str
) -> None:
    sink: list[SinkItem] = []

    answer = call(_tracked("aa,b", sink))

    # str's own answer, plain all through: a split that finds no separator hands back no
    # tracked piece, though CPython hands a str subclass back as its one piece
    assert not isinstance(answer, ConcolicStr | ConcolicBool)
    assert not any(isinstance(part, ConcolicStr) for part in _parts(answer))
    assert answer == call("aa,b")
    assert sink == [Downgrade(name=name)]


def _parts(answer: object) -> list[object]:
    """The items of a list or tuple a call handed back, or nothing for any other answer."""
    return list(answer) if isinstance(answer, list | tuple) else []


# the forms pyct encodes that str refuses: the call, and the error str raises
REFUSED: dict[str, tuple[Callable[[str], object], type[Exception]]] = {
    "s.split('')": (lambda s: s.split(""), ValueError),
    "s.partition('')": (lambda s: s.partition(""), ValueError),
    "s.center(9, '**')": (lambda s: s.center(9, "**"), TypeError),
    # each call below is one str refuses, on purpose
    "s.split(None, None)": (lambda s: s.split(None, None), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.isdigit(1)": (lambda s: s.isdigit(1), TypeError),  # pyrefly: ignore[bad-argument-count]
    "s.upper(1)": (lambda s: s.upper(1), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.strip(chars=' ')": (lambda s: s.strip(chars=" "), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.zfill(9, '*')": (lambda s: s.zfill(9, "*"), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.center()": (lambda s: s.center(), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.split(',', 1, 2)": (lambda s: s.split(",", 1, 2), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.partition(None)": (lambda s: s.partition(None), TypeError),  # pyrefly: ignore[no-matching-overload]
}


@pytest.mark.parametrize(("call", "error"), REFUSED.values(), ids=list(REFUSED))
def test_a_form_str_refuses_raises_as_the_targets_and_records_nothing(
    call: Callable[[str], object], error: type[Exception]
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(error) as raised:
        call(_tracked("a,b", sink))

    assert raised_by_target(raised.value)
    assert sink == []


def test_the_plain_text_of_anything_but_a_str_is_an_error() -> None:
    # core reads the text of a tracked str only; any other value is a pyct bug to name
    with pytest.raises(TypeError, match="not of int"):
        plain(1)


def test_an_rsplit_on_a_tracked_separator_records_its_downgrade_and_nothing_else() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("xabyab", expression="s", sink=sink)
    t = ConcolicStr("aba", expression="t", sink=sink)

    for limit in (-1, 1):
        s.rsplit(t, limit)
    s.rsplit(t)

    # whether the separator overlaps itself is pyct's question, asked of no tracked value
    assert sink == [Downgrade(name="rsplit")] * 3
