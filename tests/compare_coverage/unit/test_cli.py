"""The command line: its flags, their checks, and the exit codes ``main`` gives."""

import json
import os
from pathlib import Path

import pytest

from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage import cli
from tools.compare_coverage.cli import Flags, UsageError, main, parse_flags
from tools.compare_coverage.compare import exit_code
from tools.compare_coverage.entries import Unlisted
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


def test_a_relative_legacy_checkout_is_taken_from_the_working_directory() -> None:
    assert parse_flags(["--legacy", "a/../legacy"]).legacy == Path.cwd() / "legacy"


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


@pytest.fixture
def small_list(
    tmp_path: Path, stub_checkout: StubCheckout, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """A list over a v2 checkout with one listed and one new target, and an old fixture."""
    v2 = tmp_path / "v2"
    (v2 / "targets").mkdir(parents=True)
    fixtures = stub_checkout.path / "tests" / "acceptance" / "fixtures"
    fixtures.mkdir(parents=True)
    for file in (v2 / "targets" / "listed.py", v2 / "targets" / "new.py", fixtures / "old.py"):
        file.write_text("def f(x):\n    return x\n")
    sets = {
        "v2": {"origin": "v2", "scan": "targets"},
        "fixtures": {"origin": "legacy", "scan": "tests/acceptance/fixtures"},
    }
    entries = [{"set": "v2", "target": "targets.listed::f", "seed": {"x": 0}}]
    list_file = tmp_path / "targets.json"
    list_file.write_text(json.dumps({"sets": sets, "entries": entries}))
    monkeypatch.setattr(cli, "LIST_FILE", list_file)
    monkeypatch.setattr(cli, "REPO_ROOT", v2)
    return v2 / "targets" / "new.py", fixtures / "old.py"


def test_prepare_scans_every_set_with_no_flag_and_waits_the_full_grace(
    stub_checkout: StubCheckout, small_list: tuple[Path, Path]
) -> None:
    new, old = small_list

    run, _ = cli.prepare(["--legacy", str(stub_checkout.path)], os.environ)

    assert run.unlisted == (Unlisted("v2", new), Unlisted("fixtures", old))
    assert run.grace == 60
    assert [entry.target for entry in run.entries] == ["targets.listed::f"]


def test_prepare_scans_only_the_named_sets(
    stub_checkout: StubCheckout, small_list: tuple[Path, Path]
) -> None:
    new, _ = small_list
    legacy = ["--legacy", str(stub_checkout.path)]

    by_set, _ = cli.prepare([*legacy, "--set", "v2"], os.environ)
    by_target, _ = cli.prepare([*legacy, "--target", "targets.listed::f"], os.environ)

    assert by_set.unlisted == (Unlisted("v2", new),)
    assert by_target.unlisted == ()


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
