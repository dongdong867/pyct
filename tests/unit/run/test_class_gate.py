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
from pyct.run.llm_seeds import NOT_THE_USER_S, ClassGate
from pyct.run.target import load_target

GREET = "targets.llm.shop.greet"
MODELS = "targets.llm.shop.models"
# a module of the user's own code the gate tests import from ``tmp_path``
USER = "acme_gate_user"


def refused(text: str) -> list[str]:
    """The one line the gate gives for ``{"c": {"__class__": text}}`` when it refuses it as a
    library's."""
    return [f"c['__class__'] {NOT_THE_USER_S} \"{text}\""]


def asked(gate: ClassGate, text: str) -> list[str]:
    return gate.refusals({"c": {"__class__": text}})


@pytest.fixture
def user_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``USER``, imported, holding ``concurrent.futures`` as ``cf`` from a fresh import, so its
    lazy ``ProcessPoolExecutor`` is not read yet, a nested class and an instance."""
    (tmp_path / f"{USER}.py").write_text(
        "import concurrent.futures as cf\n\n\n"
        "class Outer:\n    class Inner:\n        def __init__(self, x):\n"
        "            self.x = x\n\n\nholder = Outer()\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(concurrent, "futures", concurrent.futures)
    for name in [name for name in sys.modules if name.startswith("concurrent.futures")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.delitem(sys.modules, USER, raising=False)
    importlib.import_module(USER)


@pytest.mark.usefixtures("user_module")
def test_a_name_that_steps_into_a_library_s_module_is_refused_without_reading_it() -> None:
    gate = ClassGate(USER, frozenset())

    assert asked(gate, f"{USER}::cf.ProcessPoolExecutor") == refused(
        f"{USER}::cf.ProcessPoolExecutor"
    )
    assert asked(gate, "cf.ThreadPoolExecutor") == refused("cf.ThreadPoolExecutor")
    assert "concurrent.futures.process" not in sys.modules
    assert "concurrent.futures.thread" not in sys.modules


@pytest.mark.usefixtures("user_module")
def test_a_name_that_steps_through_something_other_than_a_class_is_refused() -> None:
    gate = ClassGate(USER, frozenset())

    assert asked(gate, f"{USER}::holder.Inner") == refused(f"{USER}::holder.Inner")


@pytest.mark.usefixtures("user_module")
def test_a_nested_class_of_the_user_s_and_a_name_the_module_lacks_pass_to_the_checks() -> None:
    gate = ClassGate(USER, frozenset())

    assert asked(gate, f"{USER}::Outer.Inner") == []
    assert asked(gate, f"{USER}::Outer.Missing") == []
    assert asked(gate, f"{USER}::holder") == []


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
