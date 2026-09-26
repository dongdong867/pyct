"""The command line: its flags, their checks, and the exit codes ``main`` gives."""

from pathlib import Path

import pytest

from tools.compare_coverage import cli
from tools.compare_coverage.cli import Flags, UsageError, main, parse_flags
from tools.compare_coverage.compare import exit_code
from tools.compare_coverage.rows import Row, Status
from tools.compare_coverage.sides import Limits


def test_no_flags_but_legacy_give_pyct_runs_default_limits() -> None:
    flags = parse_flags(["--legacy", "/l"])

    assert flags == Flags(
        legacy=Path("/l"),
        sets=(),
        targets=(),
        limits=Limits(budget=30.0, plateau=5, solver_timeout=10.0),
        accepted=None,
        accept=False,
    )


def test_sets_and_targets_repeat() -> None:
    flags = parse_flags(["--set", "a", "--target", "m::f", "--set", "b", "--target", "m::g"])

    assert (flags.sets, flags.targets) == (("a", "b"), ("m::f", "m::g"))


@pytest.mark.parametrize(
    ("flags", "says"),
    [
        (["--budget", "soon"], "--budget must be a number of seconds, got 'soon'"),
        (["--budget", "nan"], "--budget must be a finite number of seconds above zero"),
        (["--plateau", "0"], "--plateau must be a whole number above zero, got '0'"),
        (["--plateau", "x"], "--plateau must be a whole number above zero, got 'x'"),
        (["--solver-timeout", "-1"], "--solver-timeout must be a finite number of seconds"),
        (["--budget"], "expected one argument"),
    ],
)
def test_a_limit_pyct_run_would_refuse_is_refused(flags: list[str], says: str) -> None:
    with pytest.raises(UsageError, match=says):
        parse_flags(flags)


def test_ctrl_c_exits_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(*_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "prepare", lambda _argv, _environ: (None, None))
    monkeypatch.setattr(cli, "compare", interrupted)

    assert main(["--legacy", "/l"]) == 130


def test_a_usage_error_exits_2_before_anything_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--plateau", "0"]) == 2

    out, err = capsys.readouterr()
    assert out == ""
    assert "--plateau must be a whole number above zero" in err


def row(status: Status, record: str | None = None) -> Row:
    return Row(set="v2", status=status, file="/t.py", record=record)


def test_the_exit_is_0_when_every_row_passes() -> None:
    passing = [row(Status.SAME), row(Status.LEFT_OUT), row(Status.DIFFERS, "accepted")]

    assert exit_code(passing, accepting=False) == 0


def test_the_exit_is_1_for_any_other_row_unless_accepting() -> None:
    for failing in (row(Status.DIFFERS), row(Status.SAME, "changed"), row(Status.V2_FAILED)):
        assert exit_code([row(Status.SAME), failing], accepting=False) == 1
        assert exit_code([row(Status.SAME), failing], accepting=True) == 0


def test_a_file_no_entry_names_exits_1_even_when_accepting() -> None:
    assert exit_code([row(Status.NOT_LISTED)], accepting=True) == 1
