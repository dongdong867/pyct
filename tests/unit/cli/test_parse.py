import pytest

from pyct.cli import RunCommand, UsageError, parse_command, parse_solver_timeout
from pyct.config.solver_timeout import SolverTimeout


def test_seed_may_follow_the_target() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}']) == RunCommand(
        spec="m::f", seed_text='{"x": 1}'
    )


def test_seed_may_come_through_the_args_flag() -> None:
    assert parse_command(["run", "m::f", "--args", '{"x": 1}']) == RunCommand(
        spec="m::f", seed_text='{"x": 1}'
    )


def test_seed_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]) == RunCommand(spec="m::f", seed_text=None)


def test_the_budget_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--budget", "1.5"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', budget_text="1.5"
    )


def test_the_budget_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]).budget_text is None


def test_the_plateau_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--plateau", "3"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', plateau_text="3"
    )


def test_the_plateau_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]).plateau_text is None


def test_the_solver_timeout_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--solver-timeout", "2.5"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', solver_timeout_text="2.5"
    )


def test_the_solver_timeout_may_be_absent() -> None:
    assert parse_command(["run", "m::f"]).solver_timeout_text is None


def test_parse_solver_timeout_returns_the_seconds() -> None:
    assert parse_solver_timeout("2.5") == SolverTimeout(seconds=2.5)


def test_parse_solver_timeout_without_the_flag_is_the_default_limit() -> None:
    assert parse_solver_timeout(None) == SolverTimeout()


@pytest.mark.parametrize("text", ["0", "-1", "abc", "", "1s", "nan", "inf", "1e400"])
def test_parse_solver_timeout_refuses_anything_but_a_positive_number(text: str) -> None:
    with pytest.raises(UsageError, match="solver timeout") as refused:
        parse_solver_timeout(text)

    # the value is named as it was typed, so the text can be found on the command line
    assert repr(text) in str(refused.value)
