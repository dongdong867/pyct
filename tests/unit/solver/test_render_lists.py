"""Tracked lists written for cvc5: declared as a length and arrays, read split at their pieces,
and answered back as each list's new length and the items a fork read."""

import json
import time
from typing import Any

import pytest

from pyct.binding.annotations import Items
from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.binding.shapes import ArrayValue, ListShape
from pyct.core.branch import Branch, Expression, SinkItem, Site
from pyct.solver import cvc5 as cvc5_module
from pyct.solver.answer import Sat, SolverAnswerError, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.declared import Program
from pyct.solver.list_reader import RenderTimeError
from pyct.solver.list_terms import FALSE, TRUE, Lin, both, either, ite
from pyct.solver.lists import Origin, UnencodedError
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
    with pytest.raises(UnencodedError, match="no <class 'int'> item is read there"):
        program((fork(["==", ["[]", ["[,]", 1, "'a'"], 1], 1]),), {}, {})
    # two reads of items of two kinds, compared: nothing on the path says which kind either is
    mixed: Expression = ["[,]", 1, "'a'"]
    with pytest.raises(UnencodedError, match="no value a condition reads"):
        program((fork(["==", ["[]", mixed, 0], ["[]", mixed, 1]]),), {}, {})


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


@needs_cvc5
def test_a_list_repeated_many_times_is_read_as_one_piece_and_kept_to_a_million_items() -> None:
    repeated: Expression = ["*", "items", 200_000]
    forks = (
        fork([">", ["len", repeated], 199_999]),
        fork([">", ["[]", repeated, 199_999], 5]),
    )
    seed = Seed.of({"items": [1]})

    started = time.perf_counter()
    text = program(forks, seed.leaves, seed.lists).text
    written = time.perf_counter() - started
    answer = solve(forks, seed.leaves, 10.0, seed.lists)

    assert written < 0.5 and len(text) < 5_000
    assert isinstance(answer, Sat)
    items = apply(seed, answer.model).args["items"]
    # the list the target builds from the answer holds at most a million items too
    assert isinstance(items, list) and 1 <= len(items) * 200_000 <= 1_000_000
    assert (items * 200_000)[199_999] > 5


def _appended(times: int) -> Expression:
    """``items`` with ``times`` values appended one at a time, as a loop of appends writes it."""
    form: Expression = "items"
    for value in range(times):
        form = ["+", form, ["[,]", value]]
    return form


def test_writing_a_long_read_stops_at_the_solves_deadline() -> None:
    appended = _appended(2_000)
    forks = (fork(["==", ["[]", appended, "i"], 7]),)

    with pytest.raises(RenderTimeError):
        program(forks, {"i": int}, {"items": ListShape(("int",), fill="int")}, time.monotonic())


def test_a_solve_whose_program_outlives_its_limit_is_a_timeout() -> None:
    forks = (fork(["==", ["[]", _appended(2_000), "i"], 7]),)

    answer = solve(forks, {"i": int}, 1e-6, {"items": ListShape(("int",), fill="int")})

    assert isinstance(answer, Timeout)


def test_a_path_nothing_types_a_read_of_is_an_unknown_not_a_crash() -> None:
    mixed: Expression = ["[,]", 1, "'a'"]
    forks = (fork(["==", ["[]", mixed, 0], ["[]", mixed, 1]]),)

    assert isinstance(solve(forks, {}, 5.0, {}), Unknown)


def test_a_list_changed_in_place_at_a_plain_index_is_written_in_one_row() -> None:
    form: Expression = "items"
    forks = [fork([">", ["len", "items"], 0])]
    for value in range(60):
        forks.append(fork([">", ["len", form], 0]))
        after: Expression = ["[:]", ["[:]", form, 0, None], 1, None]
        form = ["+", ["+", ["[:]", form, None, 0], ["[,]", value]], after]
    forks.append(fork([">", ["[]", form, 0], 100]))

    started = time.perf_counter()
    text = program(tuple(forks), {}, {"items": ListShape(("int",), fill="int")}).text

    assert time.perf_counter() - started < 0.5 and len(text) < 50_000


def _changed(change: str, times: int) -> tuple[Seed, tuple[Branch, ...]]:
    """The path of ``times`` changes of one kind to a tracked list, then a fork on an item,
    the fork flipped, and the input it came from."""
    args: dict[str, object] = {"items": [1, 2, 3], "i": 1}
    sink: list[SinkItem] = []
    bound = bind(args, sink)
    items: Any = bound["items"]
    i = bound["i"]
    for value in range(times):
        if change == "slice assignment":
            items[1:2] = [value]
        elif change == "slice deletion":
            items.insert(1, value)
            del items[1:2]
        else:
            items[i] = value
    bool(items[2] > 100)
    forks = [item for item in sink if isinstance(item, Branch)]
    last = forks[-1]
    return Seed.of(args), (*forks[:-1], Branch(last.expression, not last.taken, last.site))


@needs_cvc5
@pytest.mark.parametrize("change", ["slice assignment", "slice deletion", "tracked index"])
def test_a_list_changed_at_slices_or_a_tracked_index_many_times_renders_in_a_row(
    change: str,
) -> None:
    seed, path = _changed(change, 24)

    started = time.perf_counter()
    text = program(path, seed.leaves, seed.lists, None, Origin(seed.values, settle=True)).text
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)
    spent = time.perf_counter() - started

    assert len(text) < 100_000, len(text)
    assert isinstance(answer, Sat), answer
    assert spent < 5, spent
    # the answer takes the path: the item past the changes is the input's own, raised
    solved: Any = apply(seed, answer.model).args
    assert solved["items"][2] > 100


REPEATED: Expression = ["*", "items", 600_000]


@needs_cvc5
@pytest.mark.parametrize(
    ("longer_than", "answer"),
    [
        # the input's own ten items are allowed: the repeat's hold never binds under them
        (5, Sat),
        # only a longer list takes the fork, and the hold keeps the answer from it: a miss
        (20, Unknown),
        # past a million items, no answer takes it with or without the hold
        (1_000_000, Unsat),
    ],
)
def test_a_list_the_target_repeats_holds_the_answers_length_not_its_own(
    longer_than: int, answer: type
) -> None:
    seed = Seed.of({"items": [0] * 10})
    forks = (
        fork([">", ["len", REPEATED], 0]),
        fork([">", ["len", "items"], longer_than]),
    )

    assert isinstance(solve(forks, seed.leaves, 10.0, seed.lists, seed.values), answer)


MIXED = {"items": ListShape(("int", "str"), fill="none")}


@pytest.mark.parametrize(
    "condition",
    [
        ["startswith", ["[]", "items", -1], "'q'"],
        ["==", ["[]", ["[]", "items", -1], 0], "'z'"],
        ["==", ["len", ["[]", "items", -1]], 2],
        ["==", ["[]", "items", -1], "'b'"],
    ],
)
def test_a_read_of_a_mixed_list_is_typed_a_str_by_what_the_path_does_with_it(
    condition: Expression,
) -> None:
    text = program((fork(condition),), {}, MIXED).text

    assert "(select |arg.items.str| (+ |arg.items.len| (- 1)))" in text
    assert "|arg.items.int|" not in text


def test_a_read_of_a_mixed_list_is_typed_an_int_by_what_the_path_does_with_it() -> None:
    text = program((fork([">", ["+", ["[]", "items", -1], 1], 5]),), {}, MIXED).text

    assert "(select |arg.items.int| (+ |arg.items.len| (- 1)))" in text


def test_a_read_through_pieces_of_other_kinds_leaves_them_out() -> None:
    joined: Expression = ["+", ["[,]", "'a'", 1, "'b'"], "items"]
    shapes = {"items": ListShape(("int",), fill="int")}

    text = program((fork(["==", ["[]", joined, "i"], "'a'"]),), {"i": int}, shapes).text

    # the list of ints holds no str, so a str read lands in the display, on one of its strs
    assert "|arg.items.int|" not in text
    assert "(ite (< p!0 3) (or (= p!0 0) (= p!0 2)) false)" in text


def test_a_read_past_every_piece_is_refused() -> None:
    shown: Expression = ["+", ["[,]", 1], ["[,]", 2]]

    with pytest.raises(UnencodedError):
        program((fork(["==", ["[]", shown, 5], 1]),), {}, {})


def test_a_display_holding_a_tracked_list_counts_it_as_a_list() -> None:
    shapes = {"items": ListShape(("int",), fill="int")}

    text = program((fork(["==", ["len", ["[,]", "items", 1]], 2]),), {}, shapes).text

    assert "(assert (= 2 2))" in text


def test_a_list_inside_at_a_position_the_model_does_not_name_is_left_out() -> None:
    grid = {"grid": ListShape(("list",), rows={0: ListShape(("int",), fill="int")}, fill="list")}
    written = program((fork([">", ["len", ["[]", "grid", "i"]], 0]),), {"i": int}, grid)

    read = written.read({"arg.grid.len": 1, "arg.grid.rows.len": _array(1)})

    assert set(read) == {"grid"}


def test_an_unsat_answer_under_clamps_settled_as_the_input_had_them_is_unknown() -> None:
    narrowed = Program(text="", names_by_symbol={}, narrowed=True)

    assert cvc5_module._unheld(narrowed, ((), {}, {}), time.monotonic() + 1, {}) == Unknown()
