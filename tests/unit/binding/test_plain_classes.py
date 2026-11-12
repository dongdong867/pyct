"""A class read from the module's or the classes' own namespaces without running code:
``plain_class`` takes such a class only when ``getattr`` would read the same class, and
``load_class`` reads such a step that way, any other step with ``getattr`` as before."""

import collections
import importlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pyct.binding import classes
from pyct.binding.classes import Unread, load_class, plain_attribute, plain_class

MODULE = "acme_plain_classes"
SOURCE = """
from collections import OrderedDict


class Outer:
    class Inner:
        pass


class Describing(type):
    def __get__(cls, instance, owner=None):
        return int


class Reading(type):
    def __getattribute__(cls, name):
        return int


class Shadowing(type):
    Inner = int


class Holder:
    class Bound(metaclass=Describing):
        pass


class Odd(metaclass=Reading):
    class Inner:
        pass


class Shadowed(metaclass=Shadowing):
    class Inner:
        pass


class Base(OrderedDict):
    pass


def __getattr__(name):
    if name == "sp":
        import subprocess

        return subprocess.Popen
    raise AttributeError(name)
"""


@pytest.fixture
def module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    (tmp_path / f"{MODULE}.py").write_text(SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    return importlib.import_module(MODULE)


def test_a_class_in_a_module_s_or_a_class_s_namespace_is_read_plainly(module: ModuleType) -> None:
    assert plain_class(module, "Outer") is module.Outer
    assert plain_class(module.Outer, "Inner") is module.Outer.Inner


@pytest.mark.parametrize(
    ("owner", "part"),
    [
        ("module", "sp"),
        ("module", "missing"),
        ("module", "__class__"),
        ("Base", "__base__"),
        ("Base", "__class__"),
        ("Holder", "Bound"),
        ("Odd", "Inner"),
        ("Shadowed", "Inner"),
    ],
    ids=[
        "module-getattr",
        "missing",
        "data-descriptor",
        "type-s-own",
        "class-s-type",
        "get",
        "getattribute",
        "type-holds-the-name",
    ],
)
def test_a_step_getattr_could_read_otherwise_is_no_plain_class(
    module: ModuleType, owner: str, part: str
) -> None:
    held = module if owner == "module" else getattr(module, owner)

    assert plain_class(held, part) is None


def test_load_class_reads_a_plain_class_without_getattr(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(owner: object, name: str) -> object:
        raise AssertionError(f"getattr({owner!r}, {name!r})")

    monkeypatch.setattr(classes, "getattr", refused, raising=False)

    assert load_class(f"{MODULE}::Outer.Inner", "x") is module.Outer.Inner


@pytest.mark.parametrize(
    ("text", "found"),
    [
        (f"{MODULE}::sp", subprocess.Popen),
        (f"{MODULE}::Holder.Bound", int),
        (f"{MODULE}::Odd.Inner", int),
        (f"{MODULE}::Base.__base__", collections.OrderedDict),
    ],
)
@pytest.mark.usefixtures("module")
def test_load_class_reads_any_other_step_with_getattr_as_before(text: str, found: type) -> None:
    assert load_class(text, "x") is found


def test_a_name_the_namespaces_lack_is_absent_unless_a_getattr_could_answer_it(
    module: ModuleType,
) -> None:
    assert plain_attribute(module, "missing") is Unread.CODE
    assert plain_attribute(module.Outer, "missing") is Unread.ABSENT
    assert plain_attribute(classes, "missing") is Unread.ABSENT
