import importlib
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from pyct.run.import_lines import import_lines

MODULE = """\
import os

def helper(flag):
    if flag:
        return 1
    return 0

READY = helper(False)

class Box:
    SIZE = 3

    def size(self):
        return self.SIZE

if __name__ == "__main__":
    print(helper(True))
"""


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    """A folder first on the import path, whose modules this test alone imports."""
    monkeypatch.syspath_prepend(str(tmp_path))
    names = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - names:
        del sys.modules[name]


def imported(name: str) -> frozenset[int]:
    """The lines of ``name``'s module that ran while it imported."""
    with import_lines(name) as lines:
        importlib.import_module(name)
    return frozenset(lines)


def test_keeps_each_line_of_the_module_the_import_ran(folder: Path) -> None:
    (folder / "ran_at_import.py").write_text(MODULE)

    # the imports, defs, class body and the guard, and helper's lines for a false flag; not the
    # line under the guard, a true flag's return, or a method no one called
    assert imported("ran_at_import") == {1, 3, 4, 6, 8, 10, 11, 13, 16}


def test_keeps_the_lines_a_package_ran_as_it_imported_the_module(folder: Path) -> None:
    package = folder / "importing_package"
    package.mkdir()
    (package / "__init__.py").write_text("from importing_package import inner\n")
    (package / "inner.py").write_text("VALUE = 1\n\ndef f(x):\n    return x\n")

    assert imported("importing_package.inner") == {1, 3}


def test_keeps_no_line_of_a_module_already_imported(folder: Path) -> None:
    (folder / "imported_before.py").write_text("VALUE = 1\n")
    importlib.import_module("imported_before")

    assert imported("imported_before") == frozenset()


def test_keeps_the_lines_before_a_raise_and_gives_its_tool_back(folder: Path) -> None:
    (folder / "raises_at_import.py").write_text("VALUE = 1\nraise ValueError('boom')\n")
    taken = [tool for tool in range(6) if sys.monitoring.get_tool(tool) is not None]

    with pytest.raises(ValueError, match="boom"), import_lines("raises_at_import") as lines:
        importlib.import_module("raises_at_import")

    assert lines == {1, 2}
    assert [tool for tool in range(6) if sys.monitoring.get_tool(tool) is not None] == taken
