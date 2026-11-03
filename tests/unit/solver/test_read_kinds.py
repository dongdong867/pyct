"""What an unsat comes to when a read may land on an item of another kind than Python read."""

from typing import Any

import pytest

from pyct.binding.bind import Seed, bind
from pyct.binding.shapes import DictShape, ListShape
from pyct.core.branch import Branch, Expression, SinkItem, Site
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.origin import Origin
from pyct.solver.read_kinds import KIND_ASKS, asked_of_each, assignments
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("t.py", 1, 0)
MIXED = {"xs": ListShape(("int", "float", "bool"))}
ROWS = {
    "g": ListShape(
        ("list", "list"), rows={0: ListShape(("int",)), 1: ListShape(("float",))}, fill="list"
    )
}


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression, taken, SITE)


def test_each_other_kind_is_one_ask_the_fewest_reads_changed_first() -> None:
    others = [frozenset({"int", "bool"}), frozenset({"bool"})]

    asks = assignments(others)

    assert asks is not None
    assert [dict(ask) for ask in asks] == [
        {1: "bool"},
        {0: "bool"},
        {0: "int"},
        {0: "bool", 1: "bool"},
        {0: "int", 1: "bool"},
    ]


def test_more_asks_than_the_bound_make_no_asks() -> None:
    three = [frozenset({"int", "bool"})] * 3

    assert KIND_ASKS < 3**3 - 1
    assert assignments(three) is None
    assert isinstance(asked_of_each(three, False, lambda kinds: Unsat()), Unknown)


def test_an_unsat_with_nothing_else_to_ask_is_the_path_s() -> None:
    assert isinstance(asked_of_each([], False, lambda kinds: Sat({})), Unsat)


def test_an_unsat_to_every_kind_is_the_path_s() -> None:
    asked: list[object] = []

    def ask(kinds: object) -> Answer:
        asked.append(kinds)
        return Unsat()

    assert isinstance(asked_of_each([frozenset({"int", "bool"})], False, ask), Unsat)
    assert len(asked) == 2


def test_a_kind_no_ask_can_write_leaves_an_unsat_unknown() -> None:
    assert isinstance(asked_of_each([], True, lambda kinds: Unsat()), Unknown)
    assert isinstance(asked_of_each([frozenset({"int"})], True, lambda kinds: Unsat()), Unknown)


def test_the_first_sat_answers_and_stops() -> None:
    answers: list[Answer] = [Unsat(), Sat({"i": 0}), Unsat()]

    answer = asked_of_each([frozenset({"int", "bool", "float"})], False, lambda _: answers.pop(0))

    assert answer == Sat({"i": 0})
    assert len(answers) == 1


def test_a_timeout_on_an_ask_is_a_timeout() -> None:
    assert isinstance(asked_of_each([frozenset({"int"})], False, lambda _: Timeout()), Timeout)


def test_an_ask_that_answers_otherwise_leaves_the_unsat_unknown() -> None:
    assert isinstance(asked_of_each([frozenset({"int"})], False, lambda _: Unknown()), Unknown)


def test_a_position_from_the_start_of_an_argument_keeps_its_kind() -> None:
    written = program((fork([">", ["[float]", "xs", 1], 2.5]),), {}, MIXED)

    assert written.other_kinds == ()


def test_a_tracked_index_may_land_on_the_list_s_other_numbers() -> None:
    written = program((fork([">", ["[float]", "xs", "i"], 2.5]),), {"i": int}, MIXED)

    assert written.other_kinds == (frozenset({"int", "bool"}),)
    # an item the solver adds holds None
    assert written.untried


def test_a_read_from_the_end_may_land_on_another_kind() -> None:
    written = program((fork([">", ["[float]", "xs", -1], 2.5]),), {}, MIXED)

    assert written.other_kinds == (frozenset({"int", "bool"}),)


def test_two_reads_of_one_index_are_one_read() -> None:
    read: Expression = ["[float]", "xs", "i"]
    path = (fork([">", read, 2.5]), fork(["<", read, 3.5]))

    assert len(program(path, {"i": int}, MIXED).other_kinds) == 1


def test_a_read_of_a_str_has_no_other_kind_to_ask() -> None:
    shapes = {"xs": ListShape(("str", "float"))}

    written = program((fork(["==", ["[str]", "xs", "i"], "'a'"]),), {"i": int}, shapes)

    assert written.other_kinds == ()
    assert written.untried


def test_a_read_of_a_sorted_display_at_a_position_keeps_its_kind() -> None:
    display: Expression = ["[,]", ["[float]", "xs", 1], ["[int]", "xs", 0]]

    assert program((fork([">", ["[float]", display, 0], 2.5]),), {}, MIXED).other_kinds == ()


def test_an_ask_types_a_bool_read_as_the_number_it_gives_it() -> None:
    origin = Origin(shapes=MIXED, read_kinds={0: "int"})

    text = program((fork(["[bool]", "xs", "i"]),), {"i": int}, origin).text

    assert "(not (= " in text and "|arg.xs.int|" in text
    assert "|arg.xs.bool|" not in text


@pytest.mark.parametrize(("kinds", "untried"), [(("float", "int"), True), (("int", "str"), False)])
def test_a_tracked_key_beside_a_float_may_land_on_another_kind(
    kinds: tuple[str, str], untried: bool
) -> None:
    origin = Origin(dicts={"d": DictShape(("a", "b"), kinds)}, values={"k": "a"})
    path = (fork(["in", "k", "d"]), fork([">", ["[]", "d", "k"], 2]))

    assert program(path, {"k": str}, origin).untried is untried


@needs_cvc5
def test_an_index_that_must_move_to_another_kind_is_answered() -> None:
    read: Expression = ["[float]", ["[]", "g", "i"], 0]
    path = (
        fork([">", ["len", "g"], "i"]),
        fork([">=", ["len", "g"], ["-", "i"]]),
        fork([">", ["len", ["[]", "g", "i"]], 0]),
        fork([">", read, 3.0]),
        fork(["==", "i", 0]),
    )

    answer = solve(path, {"i": int}, 5.0, ROWS, {"i": 1})

    assert isinstance(answer, Sat), answer
    assert answer.model["i"] == 0


@needs_cvc5
def test_a_list_of_one_kind_stays_unsat() -> None:
    shapes = {"xs": ListShape(("float", "float"), fill="float")}
    read: Expression = ["[float]", "xs", "i"]
    path = (fork([">", read, 3.0]), fork(["<", read, 1.0]))

    assert isinstance(solve(path, {"i": int}, 5.0, shapes, {"i": 0}), Unsat)


@needs_cvc5
def test_a_list_with_an_item_no_ask_can_write_is_unknown_past_an_unsat() -> None:
    read: Expression = ["[float]", "xs", "i"]
    path = (fork([">", read, 3.0]), fork(["<", read, 1.0]))

    assert isinstance(solve(path, {"i": int}, 5.0, MIXED, {"i": 1}), Unknown)


# rows beside other kinds, where a row's read finds no form on the kind the solver gives it
NO_FORM_ROWS = [
    [[[1], [1]], [[2], 0.5]],
    [[[1], [1]], [[2], True]],
    [[[2.5], [["a"], [True, 2.5], 2.5]], ["a", 2, [[2, 2.5, True]]], [False]],
]


@needs_cvc5
@pytest.mark.parametrize("g", NO_FORM_ROWS)
def test_a_path_no_program_writes_is_unknown_not_a_crash(g: list[object]) -> None:
    args: dict[str, object] = {"g": g, "i": 0, "j": 0}
    sink: list[SinkItem] = []
    bound: Any = bind(args, sink)
    bool(bound["g"][bound["i"]][bound["j"]][0] > 3.0)
    *forks, last = [item for item in sink if isinstance(item, Branch)]
    seed = Seed.of(args)
    path = (*forks, Branch(last.expression, not last.taken, last.site))

    answer = solve(path, seed.leaves, 5.0, seed.containers(), seed.values)

    assert isinstance(answer, Unknown), answer
