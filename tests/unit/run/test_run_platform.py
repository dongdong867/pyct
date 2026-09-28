"""The platform the summary line names, read once with ``sys.modules`` left as it was found.

Each test gives the read a folder of modules, first on the import path, and drops them from
``sys.modules`` again at its end, so no test sees another's.
"""

import importlib
import platform
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pyct.run.run import _platform

READ = "Test-1.0-arm64"
# how long a test waits on another thread before it fails, rather than hanging the suite
PATIENCE = 10
# a module whose import stays open until the test lets it go, so it spans the read's end
HELD = (
    "import sys\ngate = sys.modules['pyct_test_gate']\ngate.entered.set()\ngate.release.wait(10)\n"
)


class Gate:
    """What a held module's import waits on, kept in ``sys.modules`` for it to find."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A folder first on the import path; its modules leave ``sys.modules`` after the test."""
    monkeypatch.syspath_prepend(str(tmp_path))
    kept = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - kept:
        del sys.modules[name]


def a_read(monkeypatch: pytest.MonkeyPatch, during: Callable[[], object]) -> None:
    """Put a platform read in place that runs ``during`` and answers ``READ``."""

    def read() -> str:
        during()
        return READ

    monkeypatch.setattr(platform, "platform", read)


def in_a_thread(name: str, errors: list[BaseException]) -> threading.Thread:
    """A started thread that imports ``name``, noting in ``errors`` what the import raised."""

    def work() -> None:
        try:
            importlib.import_module(name)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    return thread


def test_the_read_drops_each_module_it_imported(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (folder / "readsown").mkdir()
    # a module that puts another in sys.modules itself, as pyexpat does its errors and model
    (folder / "readsown" / "__init__.py").write_text(
        "import sys, types\nsys.modules['readsown.put'] = types.ModuleType('readsown.put')\n"
    )
    (folder / "readsown" / "sub.py").write_text("")
    a_read(monkeypatch, lambda: importlib.import_module("readsown.sub"))
    kept = set(sys.modules)

    read = _platform()

    assert read == READ
    assert set(sys.modules) == kept


# drop-only-the-platform-read-s-own-imports-keeps-another-thread-s-finished-import
def test_keeps_another_thread_s_finished_import(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (folder / "quickmod.py").write_text("")
    errors: list[BaseException] = []
    a_read(monkeypatch, lambda: in_a_thread("quickmod", errors).join(PATIENCE))

    _platform()
    held = sys.modules.get("quickmod")

    assert errors == []
    assert held is not None
    assert importlib.import_module("quickmod") is held


# drop-only-the-platform-read-s-own-imports-keeps-another-thread-s-import-in-progress
def test_keeps_another_thread_s_import_in_progress(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (folder / "slowmod.py").write_text(HELD)
    gate = Gate()
    monkeypatch.setitem(sys.modules, "pyct_test_gate", gate)
    errors: list[BaseException] = []
    threads: list[threading.Thread] = []

    def during() -> None:
        threads.append(in_a_thread("slowmod", errors))
        assert gate.entered.wait(PATIENCE)

    a_read(monkeypatch, during)

    _platform()
    gate.release.set()
    threads[0].join(PATIENCE)

    assert errors == []
    assert "slowmod" in sys.modules
