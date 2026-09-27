"""An array value read back from a cvc5 model line."""

import pytest

from pyct.binding.shapes import ArrayValue
from pyct.solver.answer import SolverAnswerError, model_from
from pyct.solver.arrays import ArrayModelError, value_line


def test_a_constant_array_with_stores_holds_each_stored_value_over_its_default() -> None:
    name, value = value_line(
        "((|arg.items.int| (store (store ((as const (Array Int Int)) 0) 0 1) 3 101)))"
    )

    assert name == "arg.items.int"
    assert value == ArrayValue(0, {0: 1, 3: 101})
    assert isinstance(value, ArrayValue) and value.at(3) == 101 and value.at(9) == 0


def test_an_outer_store_hides_an_inner_one_at_the_same_position() -> None:
    _, value = value_line("((a (store (store ((as const (Array Int Int)) 0) 2 5) 2 (- 7))))")

    assert value == ArrayValue(0, {2: -7})


def test_strings_and_arrays_of_arrays_are_read_as_the_values_they_hold() -> None:
    model = model_from(
        [
            '((s.str (store ((as const (Array Int String)) "") (- 1) "z""q")))',
            "((g.rows.int (store ((as const (Array Int (Array Int Int)))"
            " ((as const (Array Int Int)) 0)) 1 (store ((as const (Array Int Int)) (- 1)) 3 9))))",
        ]
    )

    assert model["s.str"] == ArrayValue("", {-1: 'z"q'})
    assert model["g.rows.int"] == ArrayValue(ArrayValue(0), {1: ArrayValue(-1, {3: 9})})


@pytest.mark.parametrize(
    "line",
    [
        "((a (store ((as const (Array Int Int)) 0) 1 2))",
        "((a 1)) ((b 2))",
        "((a (select b 1)))",
        "((a x))",
        "((a (store ((as const (Array Int Int)) 0) x 2)))",
        "((a (store 5 1 2)))",
        "(a 1)",
    ],
)
def test_a_value_pyct_cannot_read_is_refused(line: str) -> None:
    with pytest.raises(ArrayModelError):
        value_line(line)
    with pytest.raises(SolverAnswerError, match="cannot read"):
        model_from([line])
