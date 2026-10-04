"""A split's list in core: the target's loop over it records no fork, as on origin/v2, while a
join's walk does; the list stays tracked only while the solver writes it exactly, and is
Python's own after any other change, as on origin/v2; and the strings the solver works out."""

import os
from typing import Any

import pytest

from pyct.core import substitutes
from pyct.core.branch import PYCT_ROOT, Branch, Expression, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.str_splits import a_split_s_list, worked_out
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_list_reads import tracked


def _split(sink: list[SinkItem]) -> Any:
    return ConcolicStr.made("a,b", expression="s", sink=sink).split(",")


def _walks(sink: list[SinkItem]) -> list[Expression]:
    return [item.expression for item in sink if isinstance(item, Branch)]


@pytest.mark.parametrize(
    "loop",
    [
        lambda parts: [part for part in parts],
        lambda parts: list(enumerate(parts)),
        lambda parts: list(reversed(parts)),
        lambda parts: list(parts[1:]),
        lambda parts: sorted(parts),
    ],
    ids=["a comprehension", "enumerate", "reversed", "a slice", "sorted"],
)
def test_the_target_s_loop_over_a_split_s_list_records_no_fork(loop: Any) -> None:
    sink: list[SinkItem] = []
    parts = ConcolicStr.made("a\nb\nc", expression="s", sink=sink).splitlines()

    walked = loop(parts)

    # each piece keeps its condition, and no "is there another piece" fork is recorded, by the
    # user's decision in review round 9; sorted's compares of the pieces are Python's own
    heads = [part[0] for part in _walks(sink) if isinstance(part, list)]
    assert len([*walked]) in (2, 3) and ">" not in heads, sink


def test_a_loop_in_a_library_installed_beside_pyct_records_no_fork() -> None:
    sink: list[SinkItem] = []
    parts = _split(sink)
    # a module of another package in the folder that holds pyct's: site-packages, say
    beside = compile("walked = [part for part in parts]", f"{PYCT_ROOT}{os.sep}lib.py", "exec")
    scope: dict[str, Any] = {"parts": parts}

    exec(beside, scope)

    # only pyct's own frames are pyct: this loop is the target's, and records no piece fork
    assert len(scope["walked"]) == 2 and _walks(sink) == [], sink


def test_a_join_s_walk_over_a_split_s_list_records_its_forks() -> None:
    sink: list[SinkItem] = []
    parts = _split(sink)

    "-".join(parts)  # pyrefly: ignore[bad-argument-type]
    substitutes.join("-".join, parts)

    # the join's encoding reads how many pieces it holds from its walk's forks
    split = ["split", "s", "','"]
    assert _walks(sink) == [[">", ["len", split], at] for at in range(3)], sink


def test_a_loop_over_an_argument_s_list_records_its_forks() -> None:
    items, sink = tracked(["a", "b"])

    list(items)

    assert _walks(sink) == [[">", ["len", "items"], at] for at in range(3)], sink


SPLIT: Expression = ["split", "s", "','"]


@pytest.mark.parametrize(
    ("form", "marked"),
    [
        (SPLIT, True),
        (["[:]", SPLIT, 1, None], True),
        (["[:]", SPLIT, 1, None, None], True),
        (["[:]", SPLIT, 1, None, 1], True),
        (["[:]", SPLIT, None, None, -1], True),
        (["[:]", SPLIT, None, None, 2], False),
        (["[:]", SPLIT, None, None, "k"], False),
        (["*", SPLIT, 2], False),
        (["[:]", ["[:]", SPLIT, 1, None], 1, None], True),
        (["[:]", ["[:]", SPLIT, 1, None], None, None, -1], True),
        (["[:]", ["[:]", SPLIT, 1, None], -2, None], False),
        (["[:]", SPLIT, "i", None], False),
        (["[:]", ["+", SPLIT, ["[,]", "'z'"]], 1, None], False),
        (["+", SPLIT, ["[,]", "'z'"]], True),
        (["+", ["[,]", "'z'"], ["[:]", SPLIT, None, -1]], True),
        (["+", SPLIT, "xs"], False),
        (["+", "xs", SPLIT], False),
        ("xs", False),
    ],
    ids=[
        "its own",
        "a slice",
        "a slice with no step",
        "a slice with a step of 1",
        "a reversal",
        "a slice with a step of 2",
        "a slice with a tracked step",
        "a repeat",
        "a slice of a slice",
        "a reversal of a slice",
        "a slice of a slice from its end",
        "a slice at a tracked bound",
        "a slice of a join",
        "appended to",
        "joined on a display",
        "joined",
        "joined on",
        "an argument",
    ],
)
def test_a_split_s_list_is_one_whose_items_are_its_pieces_or_the_target_s(
    form: Expression, marked: bool
) -> None:
    # a list joined with another list, an argument's say, keeps a list argument's order, and
    # its inputs are let go as v2 lets them go
    assert a_split_s_list(form) is marked


def _changed(change: Any) -> tuple[Any, list[SinkItem]]:
    """A split's list of four pieces, changed, and the sink, cleared of the split's forks."""
    sink: list[SinkItem] = []
    parts = ConcolicStr.made("a,b,c,d", expression="s", sink=sink).split(",")
    change(parts)
    sink.clear()
    return parts, sink


@pytest.mark.parametrize(
    "change",
    [
        lambda parts: parts.pop(0),
        lambda parts: parts.insert(0, "x"),
        lambda parts: parts.remove("b"),
        lambda parts: parts.__delitem__(1),
        lambda parts: parts.__setitem__(1, "x"),
        lambda parts: parts.sort(),
        lambda parts: parts.__setitem__(slice(1, 2), ["x", "y"]),
    ],
    ids=["pop(0)", "insert", "remove", "del", "an item set", "sort", "a slice set"],
)
def test_a_split_s_list_changed_at_a_position_is_python_s_own(change: Any) -> None:
    parts, sink = _changed(change)

    # as origin/v2 hands it back: its length and its walk record nothing, and every piece
    # left keeps its own condition
    assert type(len(parts)) is int and [*parts] and sink == []
    assert all(type(piece) is ConcolicStr for piece in parts if piece not in ("x", "y"))


def _piece(index: int) -> Expression:
    return ["[]", ["split", "s", "','"], index]


@pytest.mark.parametrize(
    ("change", "recorded"),
    [
        (lambda parts: parts.pop(0), []),
        (lambda parts: parts.pop(-1), []),
        (lambda parts: parts.insert(0, "x"), []),
        (lambda parts: parts.remove("b"), [["==", _piece(0), "'b'"], ["==", _piece(1), "'b'"]]),
        (lambda parts: parts.__delitem__(1), []),
        (lambda parts: parts.__setitem__(1, "x"), []),
        (lambda parts: parts.sort(), [["<", _piece(at + 1), _piece(at)] for at in range(3)]),
        (lambda parts: parts.__setitem__(slice(1, 2), ["x", "y"]), []),
        (lambda parts: parts.append(object()), []),
    ],
    ids=[
        *("pop(0)", "pop(-1)", "insert", "remove", "del", "an item set", "sort", "a slice set"),
        "an unwritten item appended",
    ],
)
def test_a_change_at_a_position_records_what_python_s_own_list_records(
    change: Any, recorded: list[Expression]
) -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    sink.clear()

    change(parts)

    # origin/v2's plain list of pieces records only its pieces' own compares: no fork on the
    # list's length, and no loss named
    assert [getattr(item, "expression", item) for item in sink] == recorded
    assert parts.expression is None


def _split_of_four(sink: list[SinkItem]) -> Any:
    return ConcolicStr.made("a,b,c,d", expression="s", sink=sink).split(",")


@pytest.mark.parametrize(
    ("change", "form"),
    [
        (lambda parts: parts.pop(), ["[:]", ["split", "s", "','"], None, -1]),
        (lambda parts: parts.append("z"), ["+", ["split", "s", "','"], ["[,]", "'z'"]]),
    ],
    ids=["pop()", "append"],
)
def test_a_split_s_list_changed_at_its_end_stays_tracked(change: Any, form: Expression) -> None:
    parts, _ = _changed(change)

    assert parts.expression == form


def test_a_split_of_a_string_the_solver_cannot_work_out_is_python_s_own_list() -> None:
    sink: list[SinkItem] = []
    text = ConcolicStr.made("a,b", expression=["+", "s", ["str", "n"]], sink=sink)

    parts = text.split(",")

    # its pieces are tracked, as on origin/v2, and the list is Python's own
    assert type(parts) is list and all(type(piece) is ConcolicStr for piece in parts)
    assert sink == []


@pytest.mark.parametrize(
    ("form", "worked"),
    [
        ("s", True),
        ("'a,b'", True),
        (["[:]", "s", 1, None], True),
        (["[]", ["split", "s", "';'"], 0], True),
        (["+", "s", "',x'"], True),
        (["*", "s", 2], True),
        (["[]", ["strip", "s"], 0], True),
        (["strip", "s"], True),
        (["replace", "s", "'a'", "'b'"], True),
        (["+", "s", ["str", "n"]], False),
        (["[:]", "s", "i", None], False),
        (["replace", "s", "t", "'b'"], False),
        (["format", "s"], False),
        (["[]", "xs", 0], False),
        (["[]", ["[:]", "xs", 0, 1], 0], False),
        (["[]", ["+", "xs", "ys"], 0], False),
        (["[]", ["[:]", ["strip", "s"], 1, None], 0], True),
        (["[]", ["+", "s", ["strip", "t"]], 0], True),
        (["split", ["[]", "xs", 0], "','"], False),
        ([], False),
    ],
)
def test_the_solver_works_out_a_string_from_arguments_literals_and_plain_operations(
    form: Expression, worked: bool
) -> None:
    assert worked_out(form) is worked


@pytest.mark.parametrize(
    ("join", "form"),
    [
        (
            lambda parts, items: parts + items,
            ["+", ["[,]", ["[]", SPLIT, 0], ["[]", SPLIT, 1]], "items"],
        ),
        (
            lambda parts, items: items + parts,
            ["+", "items", ["[,]", ["[]", SPLIT, 0], ["[]", SPLIT, 1]]],
        ),
        (lambda parts, items: parts + _split([]), None),
    ],
    ids=["the split first", "the other list first", "two splits"],
)
def test_a_split_joined_with_another_tracked_list_is_v2_s_join(join: Any, form: Expression) -> None:
    sink: list[SinkItem] = []
    items, _ = tracked(["x"])

    joined = join(_split(sink), items)

    # as origin/v2 joins its plain list of pieces: the other list joined with a display of the
    # pieces, and two such lists a plain list; no walk fork
    assert getattr(joined, "expression", None) == form
    assert type(joined) is not list or form is None
    assert _walks(sink) == [], sink


def test_a_split_s_list_changed_where_pyct_does_not_follow_hands_back_its_piece() -> None:
    parts, sink = _changed(lambda parts: None)

    taken = parts.pop(ConcolicInt.made(1, expression="i", sink=sink))

    # a tracked index into a split's list is not followed: Python pops, as on origin/v2, and
    # the piece keeps its condition, with no loss named
    assert type(taken) is ConcolicStr and taken.expression == ["[]", ["split", "s", "','"], 1]
    assert parts.expression is None and sink == []


def test_a_split_s_list_extended_by_a_tracked_list_walks_it_as_python_does() -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    others, walked = tracked(["x"])
    sink.clear()

    parts.extend(others)

    # origin/v2's plain list of pieces walks a tracked list it takes in, and is plain after
    assert parts.expression is None and sink == []
    assert _walks(walked) == [[">", ["len", "items"], 0], [">", ["len", "items"], 1]]
    assert type(len(parts)) is int and parts[4] == "x"


def test_a_tracked_list_added_to_a_split_s_list_joins_onto_its_pieces() -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    alias, (others, _) = parts, tracked(["x"])

    parts += others

    # origin/v2's plain list has no `+=`, so Python hands it to the tracked list's `__radd__`:
    # a new list, a display of the pieces joined with the other list
    pieces: Expression = ["[,]", *(_piece(at) for at in range(4))]
    assert parts.expression == ["+", pieces, "items"] and parts is not alias
    assert list.__len__(alias) == 4


@pytest.mark.parametrize(
    ("search", "answer", "compared"),
    [
        (lambda parts: "c" in parts, True, ["'c'"] * 3),
        (lambda parts: "z" in parts, False, ["'z'"] * 4),
        (lambda parts: parts.index("b"), 1, ["'b'"] * 2),
        (lambda parts: parts.count("a"), 1, ["'a'"] * 4),
    ],
    ids=["in, found", "in, not found", "index", "count"],
)
def test_a_search_of_a_split_s_list_compares_its_pieces_as_python_does(
    search: Any, answer: object, compared: list[str]
) -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    sink.clear()

    found = search(parts)

    # as origin/v2 searches its plain list of pieces, by the user's decision on review round 10:
    # each piece's compare, and no fork on how many pieces there are
    assert found == answer
    assert _walks(sink) == [["==", _piece(at), value] for at, value in enumerate(compared)], sink
    assert parts.expression == SPLIT
