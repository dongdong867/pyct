"""Once a target loads, an import pyct's own code makes comes from the standard library.

Each test loads a target from a folder that holds its own ``difflib.py``, and then imports
``difflib`` from code compiled under a file name of pyct's, as pyct's own late imports run, or
under the target's, as the target's run. Code compiled under core's folder imports as whoever
called it, pyct's code or the target's. The run package's conftest puts back ``sys.path`` and
the working directory; these tests put back ``sys.meta_path`` and ``difflib``.
"""

import importlib
import importlib.machinery
import os
import subprocess
import sys
import sysconfig
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from pyct.core.branch import PYCT_DIR
from pyct.run import own_imports
from pyct.run.own_imports import keep_own_imports
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


def function_of(file: str, source: str) -> Callable[..., object]:
    """The function ``source`` defines as ``call``, as code of ``file``, so calling it adds that
    one frame of ``file``'s and no other."""
    defined = code_of(file, source)()["call"]
    assert callable(defined)
    return defined


# pyct's core importing difflib, as it does for pyct's own code and in the target's place
CORE_IMPORTS = "def call():\n    return importlib.import_module('difflib')\n"


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


def test_core_s_import_under_pyct_s_call_comes_from_the_standard_library(folder: Path) -> None:
    load_target("target::f")
    core = function_of(f"{PYCT_DIR}core{os.sep}late.py", CORE_IMPORTS)

    # the walk passes core's frame and reaches pyct's own further out
    names = pyct_s("found = core()", {"core": core})()

    assert is_the_standard_library_s(names["found"])


def test_core_s_import_under_the_target_s_call_comes_from_its_folder(folder: Path) -> None:
    load_target("target::f")
    core = function_of(f"{PYCT_DIR}core{os.sep}late.py", CORE_IMPORTS)
    target_s = function_of(str(folder / "target.py"), "def call(core):\n    return core()\n")

    # core runs the target's own operation, so the import is the target's
    names = pyct_s("found = target_s(core)", {"target_s": target_s, "core": core})()

    assert getattr(names["found"], "MARK", None) == "folder"


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
    load_target("target::f")

    # a second target in the same process, as in-process callers of run() load them
    target = load_target("colorsys::f")

    assert target.file == str(folder / "colorsys.py")


def test_an_import_with_no_frame_past_the_standard_library_s_is_python_s(folder: Path) -> None:
    load_target("target::f")
    # a thread that runs the standard library's code alone
    thread = threading.Thread(target=importlib.import_module, args=("difflib",))
    thread.start()
    thread.join()

    assert getattr(sys.modules["difflib"], "MARK", None) == "folder"


def test_an_installed_package_s_import_under_pyct_s_call_comes_from_the_folder(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a site-packages inside the standard library's folder, as a system Python's own is
    installed = f"{own_imports._STANDARD}site-packages{os.sep}"
    monkeypatch.setattr(own_imports, "_INSTALLED", (installed,))
    load_target("target::f")
    library_s = code_of(f"{installed}lazy.py", "found = importlib.import_module('difflib')")

    names = pyct_s("found = library_s()['found']", {"library_s": library_s})()

    assert getattr(names["found"], "MARK", None) == "folder"


def test_the_finder_goes_last_when_no_path_finder_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # an earlier test's load may have left its finder in this process
    others = [
        each
        for each in sys.meta_path
        if each is not importlib.machinery.PathFinder
        and not isinstance(each, own_imports._OwnImports)
    ]
    monkeypatch.setattr(sys, "meta_path", others)

    keep_own_imports("target")

    assert sys.meta_path[:-1] == others
    assert isinstance(sys.meta_path[-1], own_imports._OwnImports)


def test_no_folder_is_installed_when_python_started_without_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "site")

    assert own_imports._installed_folders() == ()


def test_loading_the_finder_imports_no_module_of_its_own() -> None:
    # what own_imports imports itself, then own_imports: nothing more may come with it
    loads = (
        "import sys, functools, importlib.machinery, os, types, collections.abc\n"
        "import pyct.core.branch, pyct.run\n"
        "before = set(sys.modules)\n"
        "import pyct.run.own_imports\n"
        "print(sorted(set(sys.modules) - before))\n"
    )

    result = subprocess.run(
        [sys.executable, "-P", "-c", loads], capture_output=True, text=True, check=True
    )

    assert result.stdout == "['pyct.run.own_imports']\n", result.stdout


def test_a_standard_library_folder_named_through_a_link_holds_the_standard_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "link"
    link.symlink_to(os.path.dirname(os.__file__))
    monkeypatch.setattr(sys, "path", [str(link), str(tmp_path)])

    assert own_imports._standard_entries() == [str(link)]
