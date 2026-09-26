import dataclasses
import math

import pytest

from pyct.solver.answer import (
    Error,
    Sat,
    SolverAnswerError,
    Timeout,
    Unknown,
    Unsat,
    model_from,
)


def test_a_value_line_names_a_leaf_and_its_number() -> None:
    assert model_from(["((x 5))"]) == {"x": 5}


def test_a_negative_number_is_written_as_a_subtraction() -> None:
    assert model_from(["((x (- 6)))"]) == {"x": -6}


def test_every_line_of_the_answer_is_read() -> None:
    assert model_from(["((x 5))", "((y (- 6)))", "((z 0))"]) == {"x": 5, "y": -6, "z": 0}


def test_an_answer_with_no_value_lines_is_an_empty_model() -> None:
    assert model_from([]) == {}


def test_a_string_value_is_read_back_as_the_str_it_spells() -> None:
    # cvc5's own printing of a value holding a newline, a quote, two backslashes and an é
    line = '((s "a\\u{a}b""c\\u{5c}\\u{5c}d \\u{e9}"))'

    assert model_from([line]) == {"s": 'a\nb"c\\\\d é'}


def test_a_string_value_may_hold_what_closes_the_line() -> None:
    assert model_from(['((s "x)) ((y"))']) == {"s": "x)) ((y"}


def test_strings_and_numbers_are_read_from_one_answer() -> None:
    assert model_from(['((s ""))', "((x (- 6)))"]) == {"s": "", "x": -6}


# a double as cvc5 prints a Float64 value: its sign, exponent and fraction bits
FLOAT_VALUES: dict[str, tuple[str, float]] = {
    "2.5": (f"(fp #b0 #b10000000000 #b01{'0' * 50})", 2.5),
    "-0.0": (f"(fp #b1 #b{'0' * 11} #b{'0' * 52})", -0.0),
    "inf": (f"(fp #b0 #b{'1' * 11} #b{'0' * 52})", math.inf),
    "-inf": (f"(fp #b1 #b{'1' * 11} #b{'0' * 52})", -math.inf),
}


@pytest.mark.parametrize(("text", "value"), FLOAT_VALUES.values(), ids=list(FLOAT_VALUES))
def test_a_float_value_is_read_back_as_the_double_it_spells(text: str, value: float) -> None:
    model = model_from([f"((x {text}))"])

    # repr tells -0.0 from 0.0, where `==` would not
    assert repr(model["x"]) == repr(value)


def test_a_nan_value_is_read_back_as_nan() -> None:
    model = model_from([f"((x (fp #b0 #b{'1' * 11} #b1{'0' * 51})))"])

    value = model["x"]
    assert isinstance(value, float)
    assert math.isnan(value)


def test_floats_strings_and_numbers_are_read_from_one_answer() -> None:
    lines = ['((s "a"))', f"((x (fp #b0 #b01111111111 #b{'0' * 52})))", "((n 3))"]

    assert model_from(lines) == {"s": "a", "x": 1.0, "n": 3}


def test_a_float_value_cvc5_would_not_print_names_its_line() -> None:
    with pytest.raises(SolverAnswerError, match=r"\(\(x \(fp #b0 #b1 #b0\)\)\)"):
        model_from(["((x (fp #b0 #b1 #b0)))"])


def test_a_string_value_cvc5_would_not_print_names_its_line() -> None:
    with pytest.raises(SolverAnswerError, match=r'\(\(s "a\\b"\)\)'):
        model_from(['((s "a\\b"))'])


def test_a_line_the_solver_should_not_have_written_names_itself() -> None:
    with pytest.raises(SolverAnswerError, match=r"\(\(x five\)\)"):
        model_from(["((x five))"])


def test_sat_holds_the_model_and_error_holds_the_detail() -> None:
    assert Sat({"x": 5}).model == {"x": 5}
    assert Error("parse error").detail == "parse error"


@pytest.mark.parametrize("answer", [Sat({}), Unsat(), Unknown(), Timeout(), Error("why")])
def test_an_answer_cannot_be_changed(answer: object) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        answer.whatever = 1  # type: ignore[misc]


def test_a_quoted_name_is_read_without_its_bars() -> None:
    # |x| and x are one symbol to SMT-LIB, and cvc5 writes the bars only where a name needs them
    assert model_from(["((|arg.caf%C3%A9| 5))", "((leaf.0 (- 6)))"]) == {
        "arg.caf%C3%A9": 5,
        "leaf.0": -6,
    }
