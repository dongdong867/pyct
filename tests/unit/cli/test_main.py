from pathlib import Path

import pytest

from pyct.cli import main

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
