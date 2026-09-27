"""The leaves a program declares: each parameter, and each value inside an argument, under a
constant of its own that the answer is read back by."""

import json

import pytest

from pyct.binding import bind
from pyct.core.branch import Expression
from pyct.solver.answer import SolverAnswerError
from pyct.solver.render import program
from tests.unit.solver.test_render import fork, render

# a value inside an argument, as bind names it and as leaves keys it
PORT: Expression = ["[]", ["[]", "config", "'server'"], "'port'"]
FIRST: Expression = ["[]", "items", 0]
SECOND: Expression = ["[]", "items", 1]


def test_a_value_inside_an_argument_is_declared_under_a_constant_of_its_own() -> None:
    text = render((fork(["<", PORT, 1], taken=True),), {json.dumps(PORT): int})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const |leaf.0| Int)",
        "(assert (< |leaf.0| 1))",
        "(check-sat)",
        "(get-value (|leaf.0|))",
    ]


def test_two_values_inside_one_argument_are_two_constants() -> None:
    leaves = {"x": int, json.dumps(FIRST): int, json.dumps(SECOND): int}

    text = render((fork(["==", FIRST, SECOND], taken=False),), leaves)

    lines = text.splitlines()
    assert lines[1:3] == ["(declare-const |leaf.1| Int)", "(declare-const |leaf.2| Int)"]
    assert "(assert (not (= |leaf.1| |leaf.2|)))" in lines


def test_a_str_inside_an_argument_compares_as_a_string() -> None:
    text = render((fork(["==", FIRST, "'x'"], taken=True),), {json.dumps(FIRST): str})

    lines = text.splitlines()
    assert "(declare-const |leaf.0| String)" in lines
    assert '(assert (= |leaf.0| "x"))' in lines
    ordered = render(
        (fork(["<", FIRST, SECOND], taken=True),),
        {
            json.dumps(FIRST): str,
            json.dumps(SECOND): str,
        },
    )
    assert "(assert (str.< |leaf.0| |leaf.1|))" in ordered.splitlines()


def test_an_access_the_seed_does_not_hold_names_its_parameter_in_the_error() -> None:
    # not a leaf, so an operation on items, and items is no leaf either
    with pytest.raises(ValueError, match="items"):
        render((fork(["<", ["[]", "items", 5], 1], taken=True),), {json.dumps(FIRST): int})


def test_a_program_reads_its_answer_back_by_leaf() -> None:
    leaves = {"x": int, "y": int, json.dumps(PORT): int}
    path = (fork([">", ["+", "x", PORT], 1], taken=True),)

    written = program(path, leaves)

    # y is not on the path, so it is neither declared nor read
    assert written.names_by_symbol == {"arg.x": "x", "leaf.2": json.dumps(PORT)}
    assert written.read({"arg.x": 3, "leaf.2": 70000}) == {"x": 3, json.dumps(PORT): 70000}


@pytest.mark.parametrize(
    ("name", "constant"),
    [
        pytest.param("div", "|arg.div|", id="a word of the solver's own"),
        pytest.param("café", "|arg.caf%C3%A9|", id="past ascii"),
        # a **kwargs key need not be a name; a quoted symbol cannot hold `|` or a backslash
        pytest.param("a|b\\c", "|leaf.0|", id="not an identifier"),
    ],
)
def test_every_constant_is_quoted_under_pycts_own_prefix(name: str, constant: str) -> None:
    text = render((fork([">", name, 3], taken=True),), {name: int})

    assert f"(declare-const {constant} Int)" in text.splitlines()
    assert f"(assert (> {constant} 3))" in text.splitlines()


def test_an_access_is_a_leaf_by_the_steps_binding_takes(monkeypatch: pytest.MonkeyPatch) -> None:
    # an attribute is a step binding may take next; the solver follows with no change of its own
    monkeypatch.setattr(bind, "_STEPS", frozenset({"[]", "getattr"}))
    limit: Expression = ["getattr", "rule", "'limit'"]

    text = render((fork([">", limit, 100], taken=True),), {json.dumps(limit): int})

    assert "(declare-const |leaf.0| Int)" in text.splitlines()
    assert "(assert (> |leaf.0| 100))" in text.splitlines()


def test_a_model_about_a_symbol_the_program_did_not_declare_is_unreadable() -> None:
    written = program((fork(["<", "x", 10], taken=True),), {"x": int})

    with pytest.raises(SolverAnswerError, match="arg.y"):
        written.read({"arg.x": 3, "arg.y": 4})
