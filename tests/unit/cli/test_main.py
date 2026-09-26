from collections.abc import Callable
from pathlib import Path

import pytest

from pyct import cli
from pyct.cli import main
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


def test_main_says_what_it_could_not_read_from_cvc5_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)
    # a cvc5 that finds the input but puts a line pyct cannot read inside the model
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        "cat > /dev/null\n"
        "printf 'sat\\n(warning \"x\")\\n((x 10))\\n'\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    code = main(["run", TARGET, '{"x": 3}'])

    assert code == 1
    captured = capsys.readouterr()
    # the seed's line was already printed, and pyct's break is one line rather than a traceback
    assert len(captured.out.splitlines()) == 1
    assert "cvc5 answered with a value line pyct cannot read" in captured.err
    assert "Traceback" not in captured.err


def test_main_lets_a_value_error_of_its_own_escape_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only cvc5's unreadable answer is handled; a ValueError from pyct's own code is a bug."""

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
