"""Tracked lists written for cvc5: declared as a length and arrays, read split at their pieces,
and answered back as each list's new length and the items a fork read."""

import json

import pytest

from pyct.binding.annotations import Items
from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.binding.shapes import ArrayValue, ListShape
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, SolverAnswerError, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.list_terms import FALSE, TRUE, Lin, both, either, ite
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("m.py", 2, 7)
GRID: Expression = ["[]", "grid", 0]


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def answered(args: dict[str, object], *forks: Branch) -> dict[str, object]:
    """The arguments cvc5 answers for the path, from an input of these arguments."""
    seed = Seed.of(args)
    answer = solve(forks, seed.leaves, 10.0, seed.lists)
    assert isinstance(answer, Sat), answer
    return dict(apply(seed, answer.model).args)


def test_an_argument_list_is_a_bounded_length_and_an_array_per_kind() -> None:
    text = program(
        (fork(["==", ["[]", "items", 1], "'a'"]),),
        {},
        {"items": ListShape(("int", "str"), fill="none")},
    ).text

    assert "(declare-const |arg.items.len| Int)" in text
    assert "(declare-const |arg.items.str| (Array Int String))" in text
    assert "(assert (<= 0 |arg.items.len| 1000000))" in text
    assert "(assert (>= |arg.items.len| 2))" in text


@needs_cvc5
def test_a_list_inside_a_list_is_read_through_its_row() -> None:
    args: dict[str, object] = {"grid": [[1], [2, 3]]}

    solved = answered(
        args,
        fork([">", ["len", "grid"], 1]),
        fork([">", ["len", ["[]", "grid", 1]], 2]),
        fork(["==", ["[]", ["[]", "grid", 1], 2], 9]),
    )

    grid = solved["grid"]
    assert isinstance(grid, list) and grid[0] == [1]
    assert grid[1][:2] == [2, 3] and grid[1][2] == 9


@needs_cvc5
def test_a_list_added_inside_a_list_starts_empty() -> None:
    seed = Seed.of({"grid": []}, {"grid": Items(list, Items(list, int))})
    answer = solve((fork([">", ["len", "grid"], 1]),), seed.leaves, 10.0, seed.lists)

    assert isinstance(answer, Sat)
    grid = apply(seed, answer.model).args["grid"]
    assert isinstance(grid, list) and len(grid) >= 2 and all(row == [] for row in grid)


@needs_cvc5
def test_a_row_read_again_names_the_same_arrays() -> None:
    args: dict[str, object] = {"grid": [[0, 0]]}

    solved = answered(
        args,
        fork([">", ["len", "grid"], 0]),
        fork(["==", ["[]", GRID, 0], ["[]", GRID, 1]], taken=False),
    )

    row = solved["grid"][0]  # pyrefly: ignore[bad-index]
    assert row[0] != row[1]


@needs_cvc5
def test_a_backward_slice_between_bounds_clamps_as_python_does() -> None:
    args: dict[str, object] = {"items": [1, 2, 3, 4], "n": 0}
    backward: Expression = ["[:]", "items", "n", 0, -1]

    solved = answered(
        args,
        fork(["==", ["len", backward], 2]),
        fork(["==", ["[]", backward, 0], 7]),
    )

    items, n = solved["items"], solved["n"]
    assert isinstance(items, list) and isinstance(n, int)
    assert items[n:0:-1][:1] == [7] and len(items[n:0:-1]) == 2


@needs_cvc5
def test_a_read_of_ints_among_nones_keeps_the_position_on_an_int() -> None:
    # the last item is an int only where the list is two long: an added item is None
    solved = answered(
        {"items": [None, 1]},
        fork([">=", ["len", "items"], 1]),
        fork(["==", ["[]", "items", -1], 5]),
    )

    assert solved["items"] == [None, 5]


@needs_cvc5
def test_a_read_from_the_end_keeps_the_kind_the_input_has_there() -> None:
    solved = answered(
        {"items": [1, None]},
        fork([">=", ["len", "items"], 1]),
        fork(["==", ["[]", "items", -1], 5]),
    )

    # the int is at the start, so the list is one long for its last item to be that int
    assert solved["items"] == [5]


@needs_cvc5
def test_a_display_of_strs_and_a_str_argument_join() -> None:
    args: dict[str, object] = {"items": ["a"], "s": "q"}
    joined: Expression = ["+", "items", ["[,]", "s", "'z'"]]

    solved = answered(
        args,
        fork([">", ["len", joined], 1]),
        fork(["==", ["[]", joined, 1], "'w'"]),
    )

    items, s = solved["items"], solved["s"]
    assert isinstance(items, list)
    assert [*items, s, "z"][1] == "w"


def test_a_read_of_an_item_no_term_holds_writes_nothing() -> None:
    shown: Expression = ["[,]", ["[]", "items", 0], ["[]", "items", 1]]
    text = program(
        (fork([">", ["len", shown], 1]),),
        {},
        {"items": ListShape(("none", "int"), fill="none")},
    ).text

    assert "(assert (> 2 1))" in text


def test_a_read_no_item_of_its_kind_can_meet_is_refused() -> None:
    # core records neither: an index past a display raises first, and a read of an int or a
    # str by a position the kinds cannot tell is a downgrade
    with pytest.raises(ValueError, match="no <class 'int'> item is read there"):
        program((fork(["==", ["[]", ["[,]", 1, None], 5], 1]),), {}, {})
    with pytest.raises(ValueError, match="no value a condition reads"):
        program((fork(["==", ["[]", ["[,]", 1, "'a'"], 1], 1]),), {}, {})


def test_the_answer_names_a_list_by_its_access_and_a_list_inside_by_its_own() -> None:
    written = program(
        (fork([">", ["len", ["[]", "grid", 0]], 0]),),
        {},
        {"grid": ListShape(("list",), rows={0: ListShape(("int",), fill="int")}, fill="list")},
    )
    model = {"arg.grid.len": 1, "arg.grid.rows.len": _array(0, {0: 2})}

    read = written.read(model)

    assert set(read) == {"grid", json.dumps(GRID)}


def test_an_answer_with_a_length_that_is_not_a_number_is_unreadable() -> None:
    written = program((fork([">", ["len", "items"], 0]),), {}, {"items": ListShape(())})

    with pytest.raises(SolverAnswerError, match="not a number"):
        written.read({"arg.items.len": "x"})


def test_a_float_a_display_holds_is_never_written() -> None:
    with pytest.raises(ValueError, match="nothing solves a float yet"):
        program((fork(["==", "x", 1.5]),), {"x": int}, {})


def test_terms_that_hold_or_fail_fold_where_they_are_written() -> None:
    assert either(FALSE, "p") == "p" and either("p", FALSE) == "p"
    assert either("p", "q") == "(or p q)" and either(TRUE, "q") == TRUE
    assert both(TRUE, "p") == "p" and both("p", TRUE) == "p"
    assert both("p", FALSE) == FALSE and both("p", "q") == "(and p q)"
    assert ite(FALSE, "a", "b") == "b" and ite("c", "a", "a") == "a"
    assert Lin.of("n").plus(Lin(2)).times(3).text() == "(+ (* 3 n) 6)"
    assert Lin(-2).text() == "(- 2)" and Lin().number() == 0


def _array(default: object, stored: dict[int, object] | None = None) -> object:
    return ArrayValue(default, stored or {})


@needs_cvc5
def test_an_index_past_the_million_items_an_answer_holds_is_unsat() -> None:
    seed = Seed.of({"items": [0]})

    answer = solve((fork([">", ["len", "items"], 1_000_000]),), seed.leaves, 10.0, seed.lists)

    assert isinstance(answer, Unsat)
