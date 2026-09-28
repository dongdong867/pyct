"""Once a target loads, an import pyct's own code makes comes from the standard library.

Each test loads a target from a folder that holds its own ``difflib.py``, and then imports
``difflib`` from code compiled under a file name of pyct's, as pyct's own late imports run, or
under the target's, as the target's run. The run package's conftest puts back ``sys.path`` and
the working directory; these tests put back ``sys.meta_path`` and ``difflib``.
"""

import importlib
import os
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from pyct.core.branch import PYCT_DIR
from pyct.run.target import load_target

TARGET = "def f(x: int) -> int:\n    return x\n"
# what the folder's difflib holds, so a test can tell it from the standard library's
FOLDERS = "MARK = 'folder'\n"
STDLIB = f"{sysconfig.get_path('stdlib')}{os.sep}"


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The working directory, holding ``target.py`` and its own ``difflib.py``, with difflib
    not yet imported and the finders as they were put back after the test."""
    (tmp_path / "target.py").write_text(TARGET)
    (tmp_path / "difflib.py").write_text(FOLDERS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.delitem(sys.modules, "difflib", raising=False)
    monkeypatch.delitem(sys.modules, "target", raising=False)
    return tmp_path


def code_of(
    file: str, source: str, names: dict[str, object] | None = None
) -> Callable[[], dict[str, object]]:
    """A call that runs ``source`` as code of ``file``, with ``names`` among its own, and gives
    back its names."""
    code = compile(source, file, "exec")

    def run() -> dict[str, object]:
        scope: dict[str, object] = {"importlib": importlib, **(names or {})}
        exec(code, scope)
        return scope

    return run


def pyct_s(source: str, names: dict[str, object] | None = None) -> Callable[[], dict[str, object]]:
    """Code of pyct's own, as a module under pyct's folder runs it."""
    return code_of(f"{PYCT_DIR}late.py", source, names)


def is_the_standard_library_s(module: object) -> bool:
    """Whether ``module`` is the standard library's difflib, not the folder's."""
    return (
        isinstance(module, ModuleType)
        and not hasattr(module, "MARK")
        and str(module.__file__).startswith(STDLIB)
    )


# keep-pyct-s-late-imports-from-the-target-s-folder-keeps-any-late-import-of-pyct-s-from-the-folder
def test_pyct_s_late_import_comes_from_the_standard_library(folder: Path) -> None:
    load_target("target::f")

    names = pyct_s("import difflib")()

    assert is_the_standard_library_s(names["difflib"])


def test_pyct_s_import_through_the_standard_library_comes_from_it_too(folder: Path) -> None:
    load_target("target::f")

    names = pyct_s("found = importlib.import_module('difflib')")()

    assert is_the_standard_library_s(names["found"])


def test_the_target_s_import_comes_from_its_folder(folder: Path) -> None:
    load_target("target::f")

    names = code_of(str(folder / "target.py"), "import difflib")()

    assert getattr(names["difflib"], "MARK", None) == "folder"


def test_the_target_s_import_under_pyct_s_call_comes_from_its_folder(folder: Path) -> None:
    load_target("target::f")
    target_s = code_of(str(folder / "target.py"), "found = importlib.import_module('difflib')")

    # the frame nearest the import is the target's, though pyct's code called it
    names = pyct_s("found = target_s()['found']", {"target_s": target_s})()

    assert getattr(names["found"], "MARK", None) == "folder"


def test_the_target_s_own_module_comes_from_its_folder(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "colorsys", raising=False)
    (folder / "colorsys.py").write_text(TARGET)

    target = load_target("colorsys::f")

    assert target.file == str(folder / "colorsys.py")
