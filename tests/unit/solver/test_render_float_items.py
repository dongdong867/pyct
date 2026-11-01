"""A float or a bool item as cvc5 reads it: an array of its own sort, typed by the input's
position or the list's one kind, and each float read held finite on the first ask."""

import pytest

from pyct.binding.shapes import DictShape, ListShape
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.held_items import float_leaves
from pyct.solver.lists import Origin
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("m.py", 2, 7)
FLOATS = {"xs": ListShape(("float", "float"), fill="float")}
BOOLS = {"xs": ListShape(("bool",), fill="bool")}
MIXED = {"xs": ListShape(("int", "float", "bool"))}


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def test_float_and_bool_arrays_are_declared_in_their_own_sorts() -> None:
    floats = program((fork([">", ["[]", "xs", 0], 2.5]),), {}, FLOATS).text
    bools = program((fork(["[]", "xs", 0]),), {}, BOOLS).text

    assert "(declare-const |arg.xs.float| (Array Int Float64))" in floats
    assert "(declare-const |arg.xs.bool| (Array Int Bool))" in bools
    assert "(assert (select |arg.xs.bool| 0))" in bools


def test_a_row_of_floats_is_an_array_of_arrays() -> None:
    shapes = {"g": ListShape(("list",), rows={0: ListShape(("float",), fill="float")})}

    text = program((fork([">", ["[]", ["[]", "g", 0], 0], 2.5]),), {}, shapes).text

    assert "(declare-const |arg.g.rows.float| (Array Int (Array Int Float64)))" in text
    assert "(select (select |arg.g.rows.float| 0) 0)" in text


def test_each_position_of_a_mixed_list_reads_its_own_kind_with_a_guard_only_where_it_may_move() -> (
    None
):
    path = (
        fork(["==", ["[]", "xs", 0], 7]),
        fork([">", ["[]", "xs", 1], 2.5]),
        fork(["[]", "xs", 2]),
    )

    text = program(path, {}, MIXED).text

    assert "(select |arg.xs.int| 0)" in text
    assert "(select |arg.xs.float| 1)" in text
    assert "(select |arg.xs.bool| 2)" in text


def test_a_read_of_an_int_beside_a_float_is_an_int_whatever_it_is_compared_with() -> None:
    text = program((fork([">", ["[]", "xs", 0], 2.5]),), {}, MIXED).text

    assert "(select |arg.xs.int| 0)" in text
    assert "|arg.xs.float|" not in text


def test_a_read_from_the_end_of_a_list_that_holds_a_float_is_the_input_s_kind_there() -> None:
    shapes = {"xs": ListShape(("float", "int"))}

    text = program((fork([">", ["[]", "xs", -1], 2.5]),), {}, shapes).text

    assert "(select |arg.xs.int| (+ |arg.xs.len| (- 1)))" in text
    assert "|arg.xs.float|" not in text


def test_a_tracked_index_into_a_list_of_one_kind_reads_that_kind() -> None:
    text = program((fork([">", ["[]", "xs", "i"], 2.5]),), {"i": int}, FLOATS).text

    assert "(select |arg.xs.float| " in text


def test_a_read_of_a_built_list_of_one_kind_reads_that_kind() -> None:
    joined: Expression = ["+", "xs", ["[,]", 2.5]]

    text = program((fork([">", ["[]", joined, "i"], 1.0]),), {"i": int}, FLOATS).text

    assert "(select |arg.xs.float| " in text


def test_an_int_read_of_a_list_built_with_a_float_stays_an_int() -> None:
    joined: Expression = ["+", "xs", ["[,]", 2.5]]
    shapes = {"xs": ListShape(("int",), fill="int")}

    text = program((fork([">", ["[]", joined, 0], 1.0]),), {}, shapes).text

    assert "(select |arg.xs.int| 0)" in text
    assert "|arg.xs.float|" not in text


def test_a_list_of_mixed_kinds_holds_its_length_on_the_first_ask_only() -> None:
    path = (fork(["==", ["[]", "xs", 0], 7]),)

    first = program(path, {}, Origin(shapes=MIXED))
    free = program(path, {}, Origin(shapes=MIXED, keep=False))

    assert first.kept
    assert "(assert (>= |arg.xs.len| 3))" in first.text
    assert not free.kept
    assert "(assert (>= |arg.xs.len| 3))" not in free.text


def test_a_list_of_one_kind_holds_no_length() -> None:
    written = program((fork([">", ["[]", "xs", 0], 2.5]),), {}, Origin(shapes=FLOATS))

    assert not written.kept
    assert "(assert (>= |arg.xs.len| 2))" not in written.text


def test_each_float_read_is_held_finite_where_the_list_is_asked_finite() -> None:
    path = (fork([">", ["[]", "xs", 0], 2.5]), fork([">", ["[]", "xs", 1], 2.5]))

    held = program(path, {}, FLOATS, finite={"xs"}).text
    free = program(path, {}, FLOATS).text

    for at in (0, 1):
        term = f"(select |arg.xs.float| {at})"
        line = f"(assert (not (or (fp.isNaN {term}) (fp.isInfinite {term}))))"
        assert line in held
        assert line not in free


def test_a_core_program_names_each_hold_for_its_list_and_a_count() -> None:
    path = (fork([">", ["[]", "xs", 0], 2.5]), fork([">", ["[]", "xs", 1], 2.5]))

    written = program(path, {}, FLOATS, finite={"xs"}, cores=True)

    assert ":named finite!arg.xs!0)" in written.text
    assert ":named finite!arg.xs!1)" in written.text
    assert written.text.startswith("(set-option :dump-unsat-cores true)")
    assert written.holders["arg.xs"] == "xs"


def test_a_list_left_out_of_finite_stays_free_beside_one_held() -> None:
    shapes = {**FLOATS, "ys": ListShape(("float",), fill="float")}
    path = (fork([">", ["[]", "xs", 0], 2.5]), fork([">", ["[]", "ys", 0], 2.5]))

    text = program(path, {}, shapes, finite={"ys"}).text

    assert "fp.isNaN (select |arg.ys.float| 0)" in text
    assert "fp.isNaN (select |arg.xs.float| 0)" not in text


def test_a_float_value_a_dict_declares_is_held_finite_for_its_dict() -> None:
    dicts = {"d": DictShape(keys=("a",), kinds=("float",))}
    path = (fork(["in", "k", "d"]), fork([">", ["[]", "d", "k"], 2.5]))
    origin = Origin(dicts=dicts, values={"k": "a"})

    written = program(path, {"k": str}, origin, finite={"d"}, cores=True)

    assert ":named finite!dict.0!0)" in written.text
    assert written.holders["dict.0"] == "d"


@needs_cvc5
def test_a_bool_item_a_fork_asks_to_equal_five_is_unsat() -> None:
    answer = solve((fork(["==", ["[]", "xs", 0], 5]),), {}, 5.0, BOOLS)

    assert isinstance(answer, Unsat)


@pytest.mark.parametrize(
    ("shapes", "expected"),
    [
        (FLOATS, {"xs"}),
        (BOOLS, set()),
        ({"xs": ListShape(("int",), fill="int")}, set()),
    ],
)
def test_the_first_ask_holds_finite_a_list_a_fork_names_that_can_hold_a_float(
    shapes: dict[str, ListShape], expected: set[str]
) -> None:
    path = (fork(["==", ["len", "xs"], 1]),)

    assert float_leaves(path, {}, shapes) == expected


def test_the_first_ask_holds_finite_a_dict_that_can_hold_a_float() -> None:
    origin = Origin(dicts={"d": DictShape(keys=("a",), kinds=("float",))})

    assert float_leaves((fork(["in", "'a'", "d"]),), {}, origin) == {"d"}


def test_a_list_no_fork_names_is_not_held() -> None:
    assert float_leaves((fork([">", "n", 1]),), {"n": int}, FLOATS) == set()
