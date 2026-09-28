"""The platform the summary line names, read once with ``sys.modules`` left as it was found."""

import platform
import sys
import types

import pytest

from pyct.run.run import _platform

ADDED = "pyct_test_a_module_the_read_imports"


def a_read_that_imports() -> str:
    """A platform read that imports a module of its own, as the real one does on macOS."""
    sys.modules[ADDED] = types.ModuleType(ADDED)
    return "Test-1.0-arm64"


def test_the_read_drops_each_module_it_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "platform", a_read_that_imports)
    kept = set(sys.modules)

    read = _platform()

    assert read == "Test-1.0-arm64"
    assert ADDED not in sys.modules
    assert kept <= set(sys.modules)
