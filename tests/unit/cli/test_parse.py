import pytest

from pyct.cli import (
    SWEEP_USAGE,
    RunCommand,
    SweepCommand,
    UsageError,
    parse_command,
)


def run_command(argv: list[str]) -> RunCommand:
    command = parse_command(argv)
    assert isinstance(command, RunCommand)
    return command


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
    assert run_command(["run", "m::f"]).budget_text is None


def test_the_plateau_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--plateau", "3"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', plateau_text="3"
    )


def test_the_plateau_may_be_absent() -> None:
    assert run_command(["run", "m::f"]).plateau_text is None


def test_the_solver_timeout_is_read_from_its_flag() -> None:
    assert parse_command(["run", "m::f", '{"x": 1}', "--solver-timeout", "2.5"]) == RunCommand(
        spec="m::f", seed_text='{"x": 1}', solver_timeout_text="2.5"
    )


def test_the_solver_timeout_may_be_absent() -> None:
    assert run_command(["run", "m::f"]).solver_timeout_text is None


def test_the_goal_is_read_from_its_flag() -> None:
    assert run_command(["run", "m::f", "--goal", "bugs"]).goal_text == "bugs"
    assert run_command(["run", "m::f"]).goal_text is None


def test_the_run_help_names_the_cache_folder_and_its_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_command(["run", "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert ".pyct_cache/" in help_text and "PYCT_CACHE_DIR" in help_text


def test_sweep_reads_the_package_the_list_flag_and_the_limits() -> None:
    assert parse_command(["sweep", "shop", "--list"]) == SweepCommand(
        package="shop", list_only=True
    )
    assert parse_command(["sweep", "shop"]) == SweepCommand(package="shop", list_only=False)
    argv = ["--budget", "1", "--plateau", "2", "--solver-timeout", "3", "--total-budget", "4"]
    assert parse_command(["sweep", "shop", *argv, "--goal", "bugs"]) == SweepCommand(
        package="shop",
        budget_text="1",
        plateau_text="2",
        solver_timeout_text="3",
        total_budget_text="4",
        goal_text="bugs",
    )


def test_a_sweep_usage_error_shows_the_usage_of_sweep() -> None:
    with pytest.raises(UsageError) as refused:
        parse_command(["sweep"])

    assert str(refused.value).endswith(f"usage: {SWEEP_USAGE}")
