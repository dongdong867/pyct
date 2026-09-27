"""The import hook: which modules it claims, how it loads them, and how long it stays."""

import importlib
import importlib.machinery
import importlib.resources
import importlib.util
import inspect
import runpy
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.core import substitutes
from pyct.core.values import raised_by_target
from pyct.intercept import hook
from pyct.intercept.hook import Interception, current, intercepting

HELPER = "def helper(b):\n    return b is True\n"
ENTRY = "from pkghook import helper\n\n\ndef f(x):\n    return x in 'abc'\n"


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A package, pkghook, on the import path, and no module of it imported when the test ends."""
    root = tmp_path / "pkghook"
    root.mkdir()
    (root / "__init__.py").write_text("")
    (root / "helper.py").write_text(HELPER)
    (root / "entry.py").write_text(ENTRY)
    (root / "data.txt").write_text("held")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield root
    for name in [name for name in sys.modules if name.split(".")[0] in ("pkghook", "outside")]:
        del sys.modules[name]


def interception(tmp_path: Path, module: str = "pkghook.entry") -> Interception:
    return Interception(module=module, cache=tmp_path / "cache")


def test_the_scope_is_the_target_s_top_level_package() -> None:
    held = Interception(module="shop.cart", cache=Path("/c"))

    assert held.package == "shop"
    assert [held.holds(name) for name in ("shop", "shop.cart", "shop.a.b")] == [True] * 3
    assert [held.holds(name) for name in ("shopping", "other", "sho")] == [False] * 3
    assert Interception(module="mod", cache=Path("/c")).holds("mod")


def test_a_module_in_scope_loads_substituted_from_its_own_file(package: Path) -> None:
    with intercepting(interception(package.parent)):
        entry = importlib.import_module("pkghook.entry")

    assert entry.__file__ == str(package / "entry.py")
    assert entry.f.__code__.co_filename == str(package / "entry.py")
    assert "__pyct_in__" in entry.f.__code__.co_names
    assert entry.__pyct_in__ is substitutes.in_  # pyrefly: ignore[missing-attribute]
    # the module it imports is in scope too, and so is the package
    assert "__pyct_is__" in entry.helper.helper.__code__.co_names
    assert type(sys.modules["pkghook"].__loader__).__name__ == "_Loader"
    # a module with nothing to substitute binds nothing
    assert not hasattr(sys.modules["pkghook"], "__pyct_is__")
    # the file as written stays readable, and so does the package's data
    assert inspect.getsource(entry) == ENTRY
    assert importlib.resources.files("pkghook").joinpath("data.txt").read_text() == "held"
    assert not (package / "__pycache__").exists()
    assert entry.f("b") is True


def test_a_module_outside_the_scope_loads_as_python_loads_it(package: Path, tmp_path: Path) -> None:
    (tmp_path / "outside.py").write_text(HELPER)

    with intercepting(interception(package.parent)):
        outside = importlib.import_module("outside")

    assert "__pyct_is__" not in outside.helper.__code__.co_names
    assert type(outside.__loader__) is importlib.machinery.SourceFileLoader


def test_a_module_without_source_or_missing_is_left_to_python(package: Path) -> None:
    (package / "space").mkdir()
    with intercepting(interception(package.parent)):
        space = importlib.import_module("pkghook.space")
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("pkghook.missing")

    # a namespace package has no source file to substitute
    assert space.__file__ is None


def test_the_finder_skips_a_meta_path_entry_that_finds_nothing(
    package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Silent:
        """A meta path entry with no find_spec, as an old-style importer may be."""

    monkeypatch.setattr(sys, "meta_path", [Silent(), *sys.meta_path])
    with intercepting(interception(package.parent)):
        helper = importlib.import_module("pkghook.helper")

    assert "__pyct_is__" in helper.helper.__code__.co_names


def test_the_block_is_open_only_while_it_lasts(package: Path) -> None:
    held = interception(package.parent)
    before = list(sys.meta_path)
    assert current() is None

    with pytest.raises(RuntimeError), intercepting(held):
        assert current() == held
        raise RuntimeError("the run failed")

    assert current() is None
    assert sys.meta_path == before


def test_a_source_that_cannot_be_read_raises_as_the_target_s(package: Path) -> None:
    (package / "gone.py").write_text("x = 1\n")
    with intercepting(interception(package.parent)):
        spec = importlib.util.find_spec("pkghook.gone")
        (package / "gone.py").unlink()
        assert spec is not None and spec.loader is not None
        with pytest.raises(OSError) as raised:
            spec.loader.get_code("pkghook.gone")  # pyrefly: ignore[missing-attribute]

    assert raised_by_target(raised.value)


def test_runpy_runs_a_substituted_module_in_its_own_namespace(package: Path) -> None:
    (package / "tool.py").write_text("answer = 'a' in 'abc' and (1 > 0) is True\n")

    with intercepting(interception(package.parent)):
        namespace = runpy.run_module("pkghook.tool")

    assert namespace["answer"] is True


def test_a_reload_inside_the_block_of_a_module_imported_before_it_runs(package: Path) -> None:
    helper = importlib.import_module("pkghook.helper")

    with intercepting(interception(package.parent)):
        reloaded = importlib.reload(helper)

    assert reloaded.helper(True) is True


def test_two_open_blocks_over_one_package_import_it_once(package: Path) -> None:
    held = interception(package.parent)

    with intercepting(held), intercepting(held):
        helper = importlib.import_module("pkghook.helper")

    assert "__pyct_is__" in helper.helper.__code__.co_names


def test_a_python_release_the_suite_has_not_checked_runs_the_target_as_written(
    package: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(hook, "CHECKED_ON", frozenset({(3, 0)}))
    hook._unchecked.cache_clear()

    with intercepting(interception(package.parent)):
        assert current() is None
        helper = importlib.import_module("pkghook.helper")

    assert "__pyct_is__" not in helper.helper.__code__.co_names
    assert "on Python 3.0 only" in caplog.text
    hook._unchecked.cache_clear()
