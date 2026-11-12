"""The classes an LLM seed may name: the gate reads each step of the name without running code,
and refuses a library's module even when the target is inside one."""

import concurrent
import concurrent.futures
import importlib
import sys
from pathlib import Path

import pluggy
import pytest

from pyct.run.class_listing import class_listing
from pyct.run.llm_seeds import NOT_ITS_MODULE, NOT_THE_USER_S, ClassGate
from pyct.run.target import load_target

GREET = "targets.llm.shop.greet"
MODELS = "targets.llm.shop.models"
# modules of the user's own code the gate tests import from ``tmp_path``
USER = "acme_gate_user"
LAZY = "acme_gate_lazy"
PACKAGE = "acme_gate_package"
USER_SOURCE = """
import concurrent.futures as cf
import enum
from collections import OrderedDict


class Outer:
    size = 3

    class Inner:
        def __init__(self, x):
            self.x = x


holder = Outer()


class Base(OrderedDict):
    pass


class Color(enum.Enum):
    RED = 1


class Lazy(type):
    @property
    def Lazy(cls):
        raise RuntimeError("ran")


class Meta(metaclass=Lazy):
    pass


class Describing(type):
    def __get__(cls, instance, owner=None):
        return int


class Holder:
    class Bound(metaclass=Describing):
        pass
"""
LAZY_SOURCE = """
def __getattr__(name):
    if name == "cf":
        import concurrent.futures as cf

        return cf
    if name == "sp":
        import subprocess

        return subprocess.Popen
    raise AttributeError(name)
"""


def refused(text: str, reason: str = NOT_THE_USER_S) -> list[str]:
    """The one line the gate gives for ``{"c": {"__class__": text}}`` when it refuses it with
    ``reason``, by default as a library's."""
    return [f"c['__class__'] {reason} \"{text}\""]


def unread(reason: str) -> list[str]:
    """The one line the gate gives, as the seed checks write it, for a name it cannot read."""
    return [f"c['__class__']: {reason}"]


def asked(gate: ClassGate, text: str) -> list[str]:
    return gate.refusals({"c": {"__class__": text}})


@pytest.fixture
def user_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``USER``, imported, holding ``concurrent.futures`` as ``cf`` from a fresh import, so its
    lazy ``ProcessPoolExecutor`` is not read yet; ``LAZY``, whose ``__getattr__`` hands out a
    library's module and class; and ``PACKAGE``, which holds its own submodule."""
    (tmp_path / f"{USER}.py").write_text(USER_SOURCE)
    (tmp_path / f"{LAZY}.py").write_text(LAZY_SOURCE)
    (tmp_path / PACKAGE).mkdir()
    (tmp_path / PACKAGE / "__init__.py").write_text(f"from {PACKAGE} import sub\n")
    (tmp_path / PACKAGE / "sub.py").write_text("class Thing:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(concurrent, "futures", concurrent.futures)
    for name in [name for name in sys.modules if name.startswith("concurrent.futures")]:
        monkeypatch.delitem(sys.modules, name)
    for name in (USER, LAZY, PACKAGE, f"{PACKAGE}.sub"):
        monkeypatch.delitem(sys.modules, name, raising=False)
        importlib.import_module(name)


@pytest.mark.usefixtures("user_module")
def test_a_name_that_steps_into_a_module_is_refused_without_reading_it() -> None:
    gate = ClassGate(USER, frozenset())
    before = set(sys.modules)

    for text in (f"{USER}::cf.ProcessPoolExecutor", "cf.ThreadPoolExecutor"):
        assert asked(gate, text) == refused(text, NOT_ITS_MODULE)
    named = f"{PACKAGE}::sub.Thing"
    assert asked(ClassGate(PACKAGE, frozenset()), named) == refused(named, NOT_ITS_MODULE)
    assert set(sys.modules) == before


@pytest.mark.usefixtures("user_module")
def test_a_name_only_a_module_s_getattr_answers_is_refused_without_running_it() -> None:
    gate = ClassGate(LAZY, frozenset())
    before = set(sys.modules)

    assert asked(gate, f"{LAZY}::cf.ProcessPoolExecutor") == unread(
        f"{LAZY} has no class cf.ProcessPoolExecutor"
    )
    assert asked(gate, f"{LAZY}::sp") == unread(f"{LAZY} has no class sp")
    assert set(sys.modules) == before


# what a name reads as, and the line's reason after the name it reached
NOT_A_CLASS = "is not a class"
RUNS_CODE = "cannot be read without running code"


@pytest.mark.usefixtures("user_module")
@pytest.mark.parametrize(
    ("qualname", "reached", "reason"),
    [
        ("holder", "holder", NOT_A_CLASS),
        ("holder.Inner", "holder", NOT_A_CLASS),
        ("Outer.size", "Outer.size", NOT_A_CLASS),
        # each read through its type's descriptor, which getattr runs
        ("Base.__base__", "Base.__base__", RUNS_CODE),
        ("__class__", "__class__", RUNS_CODE),
        ("Base.__class__", "Base.__class__", RUNS_CODE),
        ("Color.__class__", "Color.__class__", RUNS_CODE),
        ("Meta.Lazy", "Meta.Lazy", RUNS_CODE),
        # a class whose own type defines __get__, so getattr reads what that returns
        ("Holder.Bound", "Holder.Bound", RUNS_CODE),
    ],
)
def test_a_step_that_is_not_a_class_read_without_running_code_is_refused(
    qualname: str, reached: str, reason: str
) -> None:
    gate = ClassGate(USER, frozenset())

    assert asked(gate, f"{USER}::{qualname}") == unread(f"{USER}::{reached} {reason}")


@pytest.mark.usefixtures("user_module")
def test_a_name_the_module_or_a_class_lacks_is_refused_as_the_checks_say() -> None:
    gate = ClassGate(USER, frozenset())

    for qualname in ("Missing", "Outer.Missing", "Outer.Missing.Inner"):
        assert asked(gate, f"{USER}::{qualname}") == unread(f"{USER} has no class {qualname}")


@pytest.mark.usefixtures("user_module")
def test_a_nested_class_of_the_user_s_passes() -> None:
    assert asked(ClassGate(USER, frozenset()), f"{USER}::Outer.Inner") == []


@pytest.mark.parametrize(
    ("home", "text"),
    [
        ("subprocess", "subprocess::Popen"),
        ("subprocess", "Popen"),
        (pluggy.PluginManager.__module__, f"{pluggy.PluginManager.__module__}::PluginManager"),
        (pluggy.PluginManager.__module__, "PluginManager"),
        (pluggy.PluginManager.__module__, "pluggy::HookimplMarker"),
    ],
    ids=["stdlib", "stdlib-bare", "installed", "installed-bare", "installed-package"],
)
def test_a_library_s_class_is_refused_even_for_a_target_inside_that_library(
    home: str, text: str
) -> None:
    assert asked(ClassGate(home, frozenset()), text) == refused(text)


def test_a_class_of_the_user_s_listed_module_still_passes() -> None:
    load_target(f"{GREET}::greet")
    listing = class_listing(GREET)

    assert asked(ClassGate(GREET, listing.modules), f"{MODELS}::Customer") == []


def test_a_listed_module_that_fails_to_import_passes_to_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "acme_gate_broken.py").write_text("raise RuntimeError('broken')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    gate = ClassGate(USER, frozenset({"acme_gate_broken"}))

    assert asked(gate, "acme_gate_broken::Thing") == []
    assert "acme_gate_broken" not in sys.modules
