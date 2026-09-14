import logging
import os
import subprocess
from pathlib import Path

import pytest

from pyct.solver.locate import SolverMissingError, locate, version


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


def cvc5_saying(directory: Path, *, out: str = "", code: int = 0) -> Path:
    """A cvc5 that prints what the test wants when asked for its version."""
    (directory / "out").write_text(out)
    script = directory / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        f'cat "{directory}/out"\n'
        f"exit {code}\n"
    )
    script.chmod(0o755)
    return script


def warnings_in(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        # 1.2.x wraps the number in a sentence
        ("This is cvc5 version 1.2.1 [git tag cvc5-1.2.1]", "1.2.1"),
        # 1.3.x drops the sentence and prints the number straight after the name
        ("cvc5 1.3.4 [git f3b21c4 on branch HEAD]", "1.3.4"),
        # a two-part number is a version too, and a dev build keeps what follows its number
        ("cvc5 1.3 [git f3b21c4]", "1.3"),
        ("This is cvc5 version 1.1.3-dev.196.g5f2a1b", "1.1.3-dev.196.g5f2a1b"),
    ],
)
def test_version_reads_the_bare_number_out_of_either_banner(
    tmp_path: Path, printed: str, expected: str
) -> None:
    cvc5 = cvc5_saying(tmp_path, out=f"  {printed}  \ncompiled\n")

    assert version(cvc5) == expected


def test_version_takes_the_first_line_that_says_something(tmp_path: Path) -> None:
    cvc5 = cvc5_saying(tmp_path, out="\n   \nThis is cvc5 version 1.2.1\n")

    assert version(cvc5) == "1.2.1"


def test_version_is_nothing_when_no_token_is_a_number(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # a build that ends on the word itself names no number, so the line reads as nothing
    cvc5 = cvc5_saying(tmp_path, out="  cvc5 version  \ncompiled\n")

    with caplog.at_level(logging.WARNING, logger="pyct.solver.locate"):
        assert version(cvc5) is None

    assert len(warnings_in(caplog)) == 1, caplog.text


def test_version_is_nothing_when_cvc5_exits_badly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cvc5 = cvc5_saying(tmp_path, out="This is cvc5 version 1.2.1\n", code=1)

    with caplog.at_level(logging.WARNING, logger="pyct.solver.locate"):
        assert version(cvc5) is None

    assert len(warnings_in(caplog)) == 1, caplog.text


def test_version_is_nothing_when_cvc5_prints_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cvc5 = cvc5_saying(tmp_path, out="\n  \n")

    with caplog.at_level(logging.WARNING, logger="pyct.solver.locate"):
        assert version(cvc5) is None

    assert len(warnings_in(caplog)) == 1, caplog.text


def test_version_is_nothing_when_the_executable_cannot_be_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pyct.solver.locate"):
        assert version(tmp_path / "gone") is None

    assert len(warnings_in(caplog)) == 1, caplog.text


def test_version_is_nothing_when_the_probe_runs_out_of_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cvc5 = cvc5_saying(tmp_path, out="This is cvc5 version 1.2.1\n")

    def too_slow(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=str(cvc5), timeout=1.0)

    # a real sleep would hold the suite for the probe's whole timeout
    monkeypatch.setattr(subprocess, "run", too_slow)

    with caplog.at_level(logging.WARNING, logger="pyct.solver.locate"):
        assert version(cvc5) is None

    assert len(warnings_in(caplog)) == 1, caplog.text


def test_version_never_lets_the_probe_hang_the_run(tmp_path: Path) -> None:
    """A cvc5 that waits on stdin would hang the probe; nothing is written to it."""
    script = tmp_path / "cvc5"
    script.write_text("#!/bin/sh\nPATH=/bin:/usr/bin\ncat > /dev/null\necho 'cvc5 1.3.4'\n")
    script.chmod(0o755)

    assert version(script) == "1.3.4"
