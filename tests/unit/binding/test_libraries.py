"""A class is a library's when Python's standard library or an installed distribution holds
it, unless the code whose hint names it is in the same top-level package. A module told by its
name alone has no such exception."""

import array
import collections
import datetime
import importlib
import os
import sys
import types
from pathlib import Path

import pluggy
import pytest

from pyct.binding import libraries
from pyct.binding.libraries import from_a_library, library_module, package_of
from tests.unit.binding.hint_classes import Box, Coord, Pair, Spot
from tests.unit.binding.named_classes import Point


def target() -> None:
    """A function of the user's own code, a hint's owner."""


@pytest.mark.parametrize(
    "cls",
    [
        int,
        dict,
        types.ModuleType,
        collections.deque,
        array.array,
        datetime.date,
        pluggy.PluginManager,
    ],
)
def test_a_standard_library_or_installed_class_is_a_library_s(cls: type) -> None:
    assert from_a_library(cls)
    assert from_a_library(cls, target)


@pytest.mark.parametrize("cls", [Point, Spot, Coord, Pair, Box])
def test_a_class_of_the_user_s_own_code_is_not_a_library_s(cls: type) -> None:
    assert not from_a_library(cls)
    assert not from_a_library(cls, target)


def test_a_library_s_class_is_its_own_under_a_hint_the_same_package_writes() -> None:
    assert not from_a_library(pluggy.PluginManager, pluggy.HookimplMarker)
    assert not from_a_library(collections.deque, collections.OrderedDict)


def test_a_class_whose_module_has_no_file_is_read_by_its_module_s_name() -> None:
    assert not from_a_library(type("Made", (), {"__module__": "no_such_module_here"}))
    assert from_a_library(type("Made", (), {"__module__": "itertools"}))


def test_each_portion_of_a_namespace_package_is_a_package_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own, installed = tmp_path / "proj", tmp_path / "lib" / "site-packages"
    for folder, module, body in (
        (own, "app", "def call() -> None: ...\n\n\nclass Order: ...\n"),
        (installed, "billing", "class Retry: ...\n"),
    ):
        (folder / "acmens").mkdir(parents=True)
        (folder / "acmens" / f"{module}.py").write_text(body)
        monkeypatch.syspath_prepend(str(folder))
    roots = (*libraries.LIBRARY_ROOTS, os.path.join(str(installed), ""))
    monkeypatch.setattr(libraries, "LIBRARY_ROOTS", roots)
    libraries._library_module.cache_clear()
    for name in ("acmens", "acmens.app", "acmens.billing"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    app = importlib.import_module("acmens.app")
    billing = importlib.import_module("acmens.billing")

    assert package_of("acmens.app") == "acmens.app"
    assert from_a_library(billing.Retry, app.call)
    assert not from_a_library(app.Order, app.call)
    libraries._library_module.cache_clear()


def test_a_regular_package_s_modules_share_its_package() -> None:
    assert package_of("pluggy._manager") == package_of("pluggy._hooks") == "pluggy"
    assert package_of("itertools") == "itertools"


def test_a_file_under_a_linked_spelling_of_a_root_is_a_library_s() -> None:
    assert all(root.endswith(os.sep) for root in libraries.LIBRARY_ROOTS)
    standard = os.path.join(os.path.realpath(os.path.dirname(os.__file__)), "")
    assert standard in libraries.LIBRARY_ROOTS


@pytest.mark.parametrize(
    ("name", "library"),
    [
        ("datetime", True),
        ("json.decoder", True),
        ("pluggy._hooks", True),
        ("tests.unit.binding.named_classes", False),
        ("no_such_module_here.inside", False),
    ],
)
def test_a_module_is_told_a_library_s_by_its_name(name: str, library: bool) -> None:
    assert library_module(name) is library


def test_a_module_that_is_not_loaded_is_told_by_its_top_level_name_without_importing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed, own = tmp_path / "lib" / "site-packages", tmp_path / "proj"
    for folder, name in ((installed, "acme_lib"), (own, "acme_own")):
        (folder / name).mkdir(parents=True)
        (folder / name / "__init__.py").write_text("raise RuntimeError('imported')\n")
        monkeypatch.syspath_prepend(str(folder))
    roots = (*libraries.LIBRARY_ROOTS, os.path.join(str(installed), ""))
    monkeypatch.setattr(libraries, "LIBRARY_ROOTS", roots)
    before = set(sys.modules)

    assert library_module("acme_lib.models")
    assert not library_module("acme_own.models")
    assert library_module("tabnanny")
    assert set(sys.modules) == before


def test_a_library_s_module_is_a_library_s_whichever_package_asks() -> None:
    # from_a_library excepts the hint owner's package; library_module, the LLM seeds' test, does not
    assert not from_a_library(pluggy.PluginManager, pluggy.HookimplMarker)
    assert library_module(pluggy.PluginManager.__module__)
    assert library_module("subprocess")


def test_a_module_whose_spec_has_no_file_or_folder_is_a_library_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `__hello__` is frozen into Python and missing from sys.stdlib_module_names
    monkeypatch.delitem(sys.modules, "__hello__", raising=False)
    assert "__hello__" not in sys.stdlib_module_names

    assert library_module("__hello__")
    assert "__hello__" not in sys.modules
