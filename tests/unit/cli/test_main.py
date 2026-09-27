import json
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct import cli
from pyct.cli import main
from pyct.sweep.result import SweepLimits, SweepResult, SweepStop
from pyct.sweep.sweep import Mode, SweepTell
from tests.acceptance.harness import (
    input_lines,
    let_pyct_run_in_process,
    one_line,
    summary_line,
)

TARGET = "targets.flip.one_check::classify"
BROKEN = "targets.trace.broken_import::f"

# what main calls before the run, and then the run, in the order main's docstring gives
CHECKS = (
    "check_spec",
    "parse_seed",
    "parse_budget",
    "parse_plateau",
    "parse_solver_timeout",
    "load_target",
    "check_seed_fits",
    "check_seed_types",
    "locate",
    "run",
)


def record_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Wrap each of ``CHECKS`` in ``pyct.cli`` so every call is noted, then made as before."""
    called: list[str] = []

    def recording(name: str, real: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*args: object, **kwargs: object) -> object:
            called.append(name)
            return real(*args, **kwargs)

        return wrapper

    for name in CHECKS:
        monkeypatch.setattr(cli, name, recording(name, getattr(cli, name)))
    return called


def test_main_fails_when_cvc5_is_not_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    code = main(["run", TARGET, '{"x": 3}'])

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cvc5 was not found on PATH" in captured.err
    assert str(tmp_path) in captured.err
    assert "install" in captured.err


def test_main_loads_the_target_before_it_checks_for_cvc5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    # this target raises at import, so whichever check runs first owns the message
    code = main(["run", BROKEN, '{"x": 3}'])

    assert code == 1
    captured = capsys.readouterr()
    assert "broken_import" in captured.err
    assert "cvc5" not in captured.err


def test_main_goes_on_past_an_answer_it_could_not_read_from_cvc5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    let_pyct_run_in_process(monkeypatch)
    # a cvc5 that finds the input but puts a line pyct cannot read inside the model, which
    # ends where cvc5 refuses to say why, as it does after any answer but unknown
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        "cat > /dev/null\n"
        'printf \'sat\\n(warning "x")\\n((x 10))\\n(error "no reason")\\n\'\n'
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    with caplog.at_level("WARNING", logger="pyct.solver.cvc5"):
        code = main(["run", TARGET, '{"x": 3}'])

    assert code == 0
    captured = capsys.readouterr()
    # the fork is a miss named unknown, and the run ends as it would on any miss
    misses = summary_line(captured.out)["misses"]
    assert isinstance(misses, list) and [miss["why"] for miss in misses] == ["unknown"]
    assert "cvc5 answered with a value line pyct cannot read" in caplog.text
    assert "Traceback" not in captured.err


def test_main_lets_a_value_error_of_its_own_escape_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the errors pyct names are handled; a ValueError from pyct's own code is a bug."""

    def broken_run(*args: object, **kwargs: object) -> None:
        raise ValueError("a pyct invariant broke")

    monkeypatch.setattr("pyct.cli.run", broken_run)

    with pytest.raises(ValueError, match="invariant"):
        main(["run", TARGET, '{"x": 3}'])


def test_main_ends_stderr_with_why_the_run_stopped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)

    code = main(["run", "targets.flip.no_check::echo", '{"x": 3}'])

    assert code == 0
    captured = capsys.readouterr()
    one_line(captured.out)
    # the stop reason is a fact about the run, so it comes after the last input's trace
    assert captured.err.splitlines()[-1] == "stopped: no fork to flip"


def test_main_closes_stdout_with_the_summary_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)

    code = main(["run", "targets.flip.no_check::echo", '{"x": 3}'])

    assert code == 0
    captured = capsys.readouterr()
    # the summary is the last line, after the one input line, and says the same as stderr
    summary = summary_line(captured.out)
    assert summary["stopped"] == "no fork to flip"
    assert summary["inputs"] == 1
    assert len(input_lines(captured.out)) == 1


def test_main_runs_its_checks_in_the_order_its_docstring_gives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    let_pyct_run_in_process(monkeypatch)
    called = record_calls(monkeypatch)

    code = main(["run", "targets.flip.no_check::echo", '{"x": 3}'])

    assert code == 0
    assert called == list(CHECKS)


def test_main_asks_for_a_missing_seed_after_the_import_and_before_the_seed_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)
    called = record_calls(monkeypatch)

    code = main(["run", "targets.flip.no_check::echo"])

    assert code == 2
    # no seed text means no seed to parse; the target is loaded to say what it takes
    assert called == [
        "check_spec",
        "parse_budget",
        "parse_plateau",
        "parse_solver_timeout",
        "load_target",
    ]
    assert capsys.readouterr().out == ""


def sweeps_seen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Each sweep main asks for, in place of one, which finds nothing."""
    seen: list[dict[str, object]] = []

    def sweep(package: str, *, limits: SweepLimits, mode: Mode, tell: SweepTell) -> SweepResult:
        seen.append({"package": package, "limits": limits, "mode": mode})
        return SweepResult(package, (), SweepStop.DONE, limits)

    monkeypatch.setattr(cli, "sweep", sweep)
    return seen


def test_a_sweep_runs_its_entries_with_the_default_limits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = sweeps_seen(monkeypatch)

    assert main(["sweep", "p.q"]) == 0
    assert seen == [{"package": "p.q", "limits": SweepLimits(), "mode": Mode.RUN}]
    assert json.loads(capsys.readouterr().out)["swept"] == "p.q"


def test_a_sweep_passes_on_the_limits_it_was_given_and_whether_to_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = sweeps_seen(monkeypatch)
    argv = ["--budget", "20", "--plateau", "3", "--solver-timeout", "1", "--total-budget", "9"]

    assert main(["sweep", "p", "--list", *argv]) == 0
    limits = SweepLimits(budget=20.0, plateau=3, solver_timeout=1.0, total_budget=9.0)
    assert seen == [{"package": "p", "limits": limits, "mode": Mode.LIST}]


@pytest.mark.parametrize("package", ["shop/", "shop.py", "a..b", ""])
def test_a_sweep_refuses_a_package_that_is_no_module_name(
    package: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sweep", package]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == f"PACKAGE must be a module name, got {package!r}\n"


def test_a_sweep_refuses_a_total_budget_in_the_budgets_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["sweep", "p", "--total-budget", "0"]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == "total budget must be a finite number of seconds above zero, got '0'\n"


def test_sweep_lists_a_package_without_opening_the_interception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # listing runs no target, so it reads each module as written, in a lister of its own
    def refused(spec: str) -> object:
        raise AssertionError(f"sweep opened the interception for {spec}")

    let_pyct_run_in_process(monkeypatch)
    monkeypatch.setattr(cli, "interception", refused)

    assert main(["sweep", "targets.sweep.shop", "--list"]) == 0
    assert capsys.readouterr().out
