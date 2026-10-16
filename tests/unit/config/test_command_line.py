"""The command line's limits and goal, read from their text, and each one's refusal."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.command_line import (
    UsageError,
    dump_folder,
    parse_budget,
    parse_goal,
    parse_plateau,
    parse_solver_timeout,
)
from pyct.config.goal import Goal
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout


def test_parse_budget_returns_the_seconds() -> None:
    assert parse_budget("1.5") == Budget(seconds=1.5)


def test_parse_budget_without_the_flag_is_no_deadline() -> None:
    assert parse_budget(None) == Budget()


@pytest.mark.parametrize("text", ["0", "-1", "abc", "", "1s", "nan", "inf", "1e400"])
def test_parse_budget_refuses_anything_but_a_positive_number(text: str) -> None:
    with pytest.raises(UsageError, match="budget"):
        parse_budget(text)


def test_parse_plateau_returns_the_inputs() -> None:
    assert parse_plateau("3") == Plateau(inputs=3)
    # int() reads an optional sign, so a signed whole number is a whole number
    assert parse_plateau("+3") == Plateau(inputs=3)


def test_parse_plateau_without_the_flag_is_no_plateau_stop() -> None:
    assert parse_plateau(None) == Plateau()


@pytest.mark.parametrize("text", ["0", "-1", "2.5", "1.0", "1e2", "abc", "", "3 inputs"])
def test_parse_plateau_refuses_anything_but_a_whole_number_above_zero(text: str) -> None:
    with pytest.raises(UsageError, match="plateau must be a whole number above zero"):
        parse_plateau(text)


def test_parse_goal_reads_each_goal_and_defaults_to_coverage() -> None:
    assert parse_goal("bugs") is Goal.BUGS
    assert parse_goal("coverage") is Goal.COVERAGE
    assert parse_goal(None) is Goal.COVERAGE


def test_parse_goal_refuses_any_other_value() -> None:
    with pytest.raises(UsageError, match="goal must be coverage or bugs, got 'speed'"):
        parse_goal("speed")


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


@pytest.mark.parametrize(
    ("parse", "text", "refusal"),
    [
        (parse_budget, "abc", "budget must be a number of seconds, got 'abc'"),
        (parse_budget, "0", "budget must be a finite number of seconds above zero, got '0'"),
        (parse_solver_timeout, "abc", "solver timeout must be a number of seconds, got 'abc'"),
        (
            parse_solver_timeout,
            "0",
            "solver timeout must be a finite number of seconds above zero, got '0'",
        ),
    ],
)
def test_the_two_seconds_flags_refuse_in_the_same_words(
    parse: Callable[[str | None], object], text: str, refusal: str
) -> None:
    with pytest.raises(UsageError) as refused:
        parse(text)

    assert str(refused.value) == refusal


def test_dump_folder_is_none_without_the_flag() -> None:
    assert dump_folder(None) is None


def test_dump_folder_makes_a_missing_folder(tmp_path: Path) -> None:
    folder = tmp_path / "a" / "b"

    assert dump_folder(str(folder)) == folder
    assert folder.is_dir()
    assert dump_folder(str(tmp_path / "a" / "b")) == folder


@pytest.mark.parametrize("held", [False, True])
def test_dump_folder_refuses_a_file_or_a_folder_that_holds_files(
    tmp_path: Path, held: bool
) -> None:
    (tmp_path / "f").write_text("")
    path = tmp_path if held else tmp_path / "f"
    reason = "already holds files" if held else "is not a directory"

    with pytest.raises(UsageError, match=reason) as refused:
        dump_folder(str(path))

    assert str(path) in str(refused.value)


def test_dump_folder_refuses_a_folder_it_cannot_make_or_write(tmp_path: Path) -> None:
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(UsageError, match="cannot make or read"):
            dump_folder(str(tmp_path / "new"))
    finally:
        tmp_path.chmod(0o700)
    (tmp_path / "locked").mkdir(mode=0o500)
    try:
        with pytest.raises(UsageError, match="cannot write to"):
            dump_folder(str(tmp_path / "locked"))
    finally:
        (tmp_path / "locked").chmod(0o700)
