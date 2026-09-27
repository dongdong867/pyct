"""The library probe: which version of a library an interpreter has, and where it sits."""

import importlib.metadata
import json
import platform
import runpy
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tools.compare_coverage import library_probe
from tools.compare_coverage.library_probe import installed


def test_a_library_is_its_version_and_the_folder_its_modules_sit_in() -> None:
    pytest_dist = importlib.metadata.distribution("pytest")

    assert installed("pytest", "pytest") == {
        "version": pytest_dist.version,
        "root": str(pytest_dist.locate_file("")),
        "provides": True,
    }
    assert (Path(str(installed("pytest", "pytest")["root"])) / "pytest" / "__init__.py").exists()
    assert installed("no-such-dist", "m") == {"version": None, "root": None, "provides": False}


def test_a_library_provides_only_the_modules_it_installed() -> None:
    # werkzeug sits in the same folder as pytest, but pytest's record does not hold it
    assert installed("pytest", "_pytest.python")["provides"] is True
    assert installed("pytest", "werkzeug.http")["provides"] is False
    assert installed("werkzeug", "werkzeug.http")["provides"] is True


def test_the_standard_library_is_pythons_version_and_folder() -> None:
    assert installed("python", "urllib.parse") == {
        "version": platform.python_version(),
        "root": sysconfig.get_path("stdlib"),
        "provides": True,
    }
    assert installed("python", "json")["provides"] is True
    assert installed("python", "werkzeug.http")["provides"] is False


def test_run_as_a_side_it_finds_a_copy_in_its_working_directory_first(tmp_path: Path) -> None:
    metadata = tmp_path / "werkzeug-9.9.dist-info" / "METADATA"
    metadata.parent.mkdir()
    metadata.write_text("Metadata-Version: 2.1\nName: werkzeug\nVersion: 9.9\n")

    said = subprocess.run(
        [sys.executable, "-P", library_probe.__file__, "werkzeug", "werkzeug.http"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    # its record names no file, so it provides no module
    assert json.loads(said.stdout) == {"version": "9.9", "root": str(tmp_path), "provides": False}


def test_run_as_a_script_it_prints_one_line(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", ["library_probe.py", "python", "json"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(library_probe.__file__, run_name="__main__")

    assert exited.value.code == 0
    out, _ = capfd.readouterr()
    assert json.loads(out)["version"] == platform.python_version()
