from pathlib import Path

import pytest

from pyct.cli import main
from tests.acceptance.harness import let_pyct_run_in_process

TARGET = "targets.flip.one_check::classify"
BROKEN = "targets.trace.broken_import::f"


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


def test_main_checks_for_cvc5_before_it_loads_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    # this target raises at import, so whichever check runs first owns the message
    code = main(["run", BROKEN, '{"x": 3}'])

    assert code == 1
    captured = capsys.readouterr()
    assert "cvc5" in captured.err
    assert "broken_import" not in captured.err


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
