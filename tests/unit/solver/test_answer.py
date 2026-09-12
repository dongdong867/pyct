import dataclasses

import pytest
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat, model_from


def test_a_value_line_names_a_leaf_and_its_number() -> None:
    assert model_from(["((x 5))"]) == {"x": 5}


def test_a_negative_number_is_written_as_a_subtraction() -> None:
    assert model_from(["((x (- 6)))"]) == {"x": -6}


def test_every_line_of_the_answer_is_read() -> None:
    assert model_from(["((x 5))", "((y (- 6)))", "((z 0))"]) == {"x": 5, "y": -6, "z": 0}


def test_an_answer_with_no_value_lines_is_an_empty_model() -> None:
    assert model_from([]) == {}


def test_a_line_the_solver_should_not_have_written_names_itself() -> None:
    with pytest.raises(ValueError, match=r"\(\(x five\)\)"):
        model_from(["((x five))"])


def test_sat_holds_the_model_and_error_holds_the_detail() -> None:
    assert Sat({"x": 5}).model == {"x": 5}
    assert Error("parse error").detail == "parse error"


@pytest.mark.parametrize("answer", [Sat({}), Unsat(), Unknown(), Timeout(), Error("why")])
def test_an_answer_cannot_be_changed(answer: object) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        answer.whatever = 1  # type: ignore[misc]
