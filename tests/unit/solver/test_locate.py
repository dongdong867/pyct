import os
from pathlib import Path

import pytest
from pyct.solver.locate import SolverMissingError, locate


def fake_cvc5(directory: Path) -> Path:
    """An executable named cvc5, so ``shutil.which`` has something to find."""
    executable = directory / "cvc5"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    return executable


def test_locate_returns_the_cvc5_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = fake_cvc5(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert locate() == executable


def test_locate_raises_when_the_path_has_no_cvc5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(SolverMissingError) as caught:
        locate()

    assert caught.value.searched == (str(tmp_path),)


def test_the_message_names_what_is_missing_where_it_looked_and_how_to_get_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(SolverMissingError) as caught:
        locate()

    message = str(caught.value)
    assert "cvc5 was not found on PATH" in message
    assert str(tmp_path) in message
    assert "install" in message


def test_searched_lists_every_directory_and_drops_the_empty_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    # an empty entry means the working directory, which is not a place pyct looked
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path), "", str(other)]))

    with pytest.raises(SolverMissingError) as caught:
        locate()

    assert caught.value.searched == (str(tmp_path), str(other))
