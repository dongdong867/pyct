import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pyct.run.target import load_target


@pytest.fixture
def lazy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A module in ``sys.modules`` that ``LazyLoader`` left unloaded, for this test alone. It
    keeps the lazy class ``LazyLoader`` gives it until an attribute read through it loads it."""
    file = str(tmp_path / "lazy_kept.py")
    Path(file).write_text("RAN = True\n")
    spec = importlib.util.spec_from_file_location("lazy_kept", file)
    assert spec is not None and spec.loader is not None
    spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "lazy_kept", module)
    spec.loader.exec_module(module)
    return module


def test_naming_a_file_s_module_leaves_a_lazy_module_unloaded(
    lazy: ModuleType, tmp_path: Path
) -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    other = target.module_of(str(tmp_path / "other.py"))
    own = target.module_of(str(tmp_path / "lazy_kept.py"))

    assert (other, own) == ("other", "lazy_kept")
    assert type(lazy) is not ModuleType


class Recorder:
    """An entry of ``sys.modules`` that is no module, which keeps each attribute read through it."""

    def __init__(self) -> None:
        self.read: list[str] = []

    def __getattribute__(self, name: str) -> object:
        object.__getattribute__(self, "read").append(name)
        return object.__getattribute__(self, name)


def test_naming_a_file_s_module_reads_no_attribute_of_an_entry_that_is_no_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = Recorder()
    monkeypatch.setitem(sys.modules, "recorded_entry", entry)
    target = load_target("targets.trace.uncalled_helper::classify")

    assert target.module_of("/nowhere/lost.py") == "lost"
    assert object.__getattribute__(entry, "read") == []


class Forwarding(ModuleType):
    """A module that names its file only through ``__getattr__``, as one that stands in for
    another module does."""

    def __getattr__(self, name: str) -> object:
        if name == "__file__":
            return "/elsewhere/wrapped.py"
        raise AttributeError(name)


def test_a_file_only_an_entry_s_attribute_hook_names_is_named_by_its_stem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pkg.wrapped", Forwarding("pkg.wrapped"))
    target = load_target("targets.trace.uncalled_helper::classify")

    assert target.module_of("/elsewhere/wrapped.py") == "wrapped"
