"""An array value read back from a cvc5 model line."""

from math import inf, isnan

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


TWO_AND_A_HALF = f"(fp #b0 #b10000000000 #b01{'0' * 50})"
ZERO = f"(fp #b0 #b{'0' * 11} #b{'0' * 52})"
NAN = f"(fp #b0 #b{'1' * 11} #b1{'0' * 51})"
INFINITY = f"(fp #b0 #b{'1' * 11} #b{'0' * 52})"
FLOAT64 = "(Array Int (_ FloatingPoint 11 53))"


def test_an_array_of_doubles_reads_each_double() -> None:
    line = f"((x (store ((as const {FLOAT64}) {ZERO}) 1 {TWO_AND_A_HALF})))"

    assert value_line(line) == ("x", ArrayValue(0.0, {1: 2.5}))


def test_an_array_holds_nan_and_the_infinities() -> None:
    line = f"((x (store (store ((as const {FLOAT64}) {NAN}) 0 {INFINITY}) 1 {ZERO})))"

    _, array = value_line(line)

    assert isinstance(array, ArrayValue) and isinstance(array.default, float)
    assert isnan(array.default)
    assert array.stored == {0: inf, 1: 0.0}


def test_an_array_of_bools_reads_each_bool() -> None:
    line = "((x (store ((as const (Array Int Bool)) false) 2 true)))"

    assert value_line(line) == ("x", ArrayValue(False, {2: True}))


def test_an_array_of_arrays_of_doubles_reads_each_level() -> None:
    inner = f"(store ((as const {FLOAT64}) {ZERO}) 0 {TWO_AND_A_HALF})"
    line = (
        f"((x (store ((as const (Array Int {FLOAT64})) ((as const {FLOAT64}) {ZERO})) 1 {inner})))"
    )

    assert value_line(line) == ("x", ArrayValue(ArrayValue(0.0), {1: ArrayValue(0.0, {0: 2.5})}))
