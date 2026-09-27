"""Tracked dicts written for cvc5: a presence for each key a fork names, a count of the input's
other keys kept and of keys made up, one size, and the answer read back as each dict's keys."""

import pytest

from pyct.binding.annotations import Items
from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.binding.shapes import DictAnswer, DictShape
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, SolverAnswerError, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.dict_keys import made_up_number
from pyct.solver.lists import Origin
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("m.py", 2, 7)
SERVER: Expression = ["[]", "config", "'server'"]


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def answered(
    args: dict[str, object], *forks: Branch, checks: dict[str, object] | None = None
) -> dict[str, object]:
    """The arguments cvc5 answers for the path, from an input of these arguments."""
    seed = Seed.of(args, checks)  # pyrefly: ignore[bad-argument-type]
    answer = solve(forks, seed.leaves, 10.0, seed.containers(), seed.values)
    assert isinstance(answer, Sat), answer
    return dict(apply(seed, answer.model).args)


def test_a_named_key_is_a_bool_and_a_count_declares_the_size_once() -> None:
    text = program(
        (fork(["in", "'coupon'", "order"]), fork(["!=", ["len", "order"], 0])),
        {},
        _origin({"order": DictShape(("total",), ("int",), "int")}),
    ).text

    assert "(declare-const |dict.0.in.0| Bool)" in text
    assert "(declare-const |dict.0.len| Int)" in text
    assert (
        "(assert (= |dict.0.len| (+ (ite |dict.0.in.0| 1 0) |dict.0.kept| |dict.0.made|)))" in text
    )
    assert "(assert (<= 0 |dict.0.len| 1000000))" in text
    # the first ask keeps the input's other key and makes none up
    assert "(assert (= |dict.0.kept| 1))" in text and "(assert (= |dict.0.made| 0))" in text


def _origin(dicts: dict[str, DictShape]) -> Origin:
    return Origin(dicts=dicts)


@needs_cvc5
def test_a_named_key_is_added_after_the_input_s_keys() -> None:
    solved = answered({"order": {"total": 5}}, fork(["in", "'coupon'", "order"]))

    order = solved["order"]
    assert isinstance(order, dict) and list(order) == ["total", "coupon"] and order["coupon"] == 0


@needs_cvc5
def test_a_named_key_is_removed() -> None:
    solved = answered(
        {"order": {"total": 5, "x": 1}}, fork(["in", "'total'", "order"], taken=False)
    )

    assert solved["order"] == {"x": 1}


@needs_cvc5
def test_a_count_is_met_by_made_up_keys_of_the_annotation_s_kind() -> None:
    solved = answered(
        {"config": {}},
        fork(["!=", ["len", "config"], 0]),
        checks={"config": Items(dict, int)},
    )

    assert solved["config"] == {"pyct1": 0}


@needs_cvc5
def test_a_smaller_dict_loses_its_unnamed_keys_from_its_end() -> None:
    solved = answered({"config": {"a": 1, "b": 2, "c": 3}}, fork(["==", ["len", "config"], 1]))

    assert solved["config"] == {"a": 1}


@needs_cvc5
def test_a_value_read_keeps_its_key() -> None:
    solved = answered(
        {"config": {"a": 0, "b": 0}},
        fork(["==", ["len", "config"], 1]),
        fork([">", ["[]", "config", "'b'"], 5]),
    )

    config = solved["config"]
    assert isinstance(config, dict) and list(config) == ["b"] and config["b"] > 5


@needs_cvc5
def test_a_dict_read_inside_another_keeps_its_key_there() -> None:
    solved = answered(
        {"config": {"server": {}, "x": 1}},
        fork(["==", ["len", "config"], 1]),
        fork(["in", "'port'", SERVER]),
        checks={"config": Items(dict, Items(dict, int))},
    )

    assert solved["config"] == {"server": {"port": 0}}


@needs_cvc5
def test_a_tracked_key_equals_a_key_the_dict_holds() -> None:
    solved = answered({"name": "kiwi", "prices": {"apple": 1}}, fork(["in", "name", "prices"]))

    assert solved["name"] == "apple" and solved["prices"] == {"apple": 1}


@needs_cvc5
def test_a_value_under_a_tracked_key_is_the_one_under_the_key_it_equals() -> None:
    solved = answered(
        {"name": "apple", "prices": {"apple": 1, "pear": "x"}},
        fork(["in", "name", "prices"]),
        fork([">", ["[]", "prices", "name"], 5]),
    )

    prices = solved["prices"]
    assert solved["name"] == "apple" and isinstance(prices, dict) and prices["apple"] > 5


@needs_cvc5
def test_a_tracked_key_may_equal_a_made_up_key_skipping_the_texts_taken() -> None:
    solved = answered(
        {"name": "x", "prices": {"pyct1": 1}},
        fork(["in", "name", "prices"]),
        fork(["!=", "name", "'pyct1'"]),
        fork([">", ["[]", "prices", "name"], 5]),
    )

    prices = solved["prices"]
    assert isinstance(prices, dict) and solved["name"] in prices and solved["name"] != "pyct1"
    assert prices[solved["name"]] > 5  # pyrefly: ignore[bad-index]


@needs_cvc5
def test_an_int_key_a_fork_names_is_added() -> None:
    solved = answered({"config": {}}, fork(["in", 3, "config"]))

    assert solved["config"] == {3: None}


@needs_cvc5
def test_a_dict_inside_a_list_is_read_by_its_place() -> None:
    orders: Expression = ["[]", "orders", 0]
    solved = answered(
        {"orders": [{"coupon": "x"}]},
        fork([">", ["len", "orders"], 0]),
        fork(["in", "'coupon'", orders]),
        fork(["==", ["[]", orders, "'coupon'"], "'SAVE'"]),
    )

    assert solved["orders"] == [{"coupon": "SAVE"}]


@needs_cvc5
def test_a_value_under_a_key_the_input_lacks_is_the_answer_s() -> None:
    solved = answered(
        {"config": {"a": "x"}},
        fork(["in", "'n'", "config"]),
        fork(["==", ["[]", "config", "'n'"], "'y'"]),
    )

    assert solved["config"] == {"a": "x", "n": "y"}


@needs_cvc5
def test_a_path_the_input_s_keys_cannot_take_is_unsat() -> None:
    seed = Seed.of({"config": {"a": 1, "b": "x"}})
    forks = (fork(["in", "'a'", "config"], taken=False), fork(["in", "'a'", "config"]))

    assert isinstance(solve(forks, seed.leaves, 10.0, seed.containers()), Unsat)


def test_a_read_no_int_or_str_types_is_an_unknown_miss() -> None:
    seed = Seed.of({"key": "a", "config": {"a": None}})
    forks = (fork(["==", ["[]", "config", "key"], 1]),)

    assert isinstance(solve(forks, seed.leaves, 10.0, seed.containers()), Unknown)


def test_a_dict_s_answer_names_only_what_it_declared() -> None:
    written = program(
        (fork(["in", "'a'", "config"]),), {}, _origin({"config": DictShape(("a",), ("int",))})
    )

    assert written.read({"dict.0.in.0": True}) == {
        "config": DictAnswer(present={"a": True}, kept=0, made=0)
    }
    with pytest.raises(SolverAnswerError, match="dict.9"):
        written.read({"dict.9.in.0": True})


def test_a_made_up_key_s_number_is_its_digits_written_plainly() -> None:
    assert made_up_number("pyct12") == 12
    assert [made_up_number(text) for text in ("pyct", "pyct01", "pyct1a", "x1", 3)] == [None] * 5


@needs_cvc5
def test_a_tracked_key_may_keep_a_later_key_and_drop_an_earlier_one() -> None:
    solved = answered(
        {"name": "x", "prices": {"a": 1, "b": 2}},
        fork(["==", "name", "'b'"]),
        fork(["in", "name", "prices"]),
        fork(["==", ["len", "prices"], 1]),
    )

    assert solved["name"] == "b" and solved["prices"] == {"b": 2}


@needs_cvc5
def test_a_tracked_key_keeps_the_input_s_keys_where_the_path_allows() -> None:
    solved = answered(
        {"name": "x", "prices": {"a": 1, "b": 2, "c": 3}},
        fork(["in", "name", "prices"]),
        fork(["!=", "name", "'a'"]),
    )

    assert solved["prices"] == {"a": 1, "b": 2, "c": 3} and solved["name"] in ("b", "c")


@needs_cvc5
def test_a_value_read_by_a_literal_and_a_tracked_key_is_one_constant() -> None:
    solved = answered(
        {"name": "x", "prices": {"apple": 1}},
        fork([">", ["[]", "prices", "'apple'"], 0]),
        fork(["in", "name", "prices"]),
        fork([">", ["[]", "prices", "name"], 5]),
        fork([">", ["[]", "prices", "name"], 6]),
    )

    prices = solved["prices"]
    assert solved["name"] == "apple" and isinstance(prices, dict) and prices["apple"] > 6


@needs_cvc5
def test_a_tracked_int_key_equals_an_int_key() -> None:
    solved = answered(
        {"n": 0, "config": {1: 5, "a": 2}},
        fork(["in", "n", "config"]),
        fork([">", ["[]", "config", "n"], 7]),
    )

    config = solved["config"]
    assert solved["n"] == 1 and isinstance(config, dict) and config[1] > 7
