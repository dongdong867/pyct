import contextlib
import importlib
import inspect
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

from pyct.run.import_watch import ImportWatch
from pyct.run.target import Target, TargetError, load_target

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_target_imports_from_the_current_directory() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    assert isinstance(target, Target)
    assert target.spec == "targets.trace.uncalled_helper::classify"
    assert target.file == str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
    assert list(target.signature.parameters) == ["x"]
    assert target.fn(x=1) == "small"


def test_load_target_names_a_module_that_does_not_import() -> None:
    with pytest.raises(TargetError, match="targets.trace.broken_import"):
        load_target("targets.trace.broken_import::anything")


def test_load_target_names_a_missing_module() -> None:
    with pytest.raises(TargetError, match="targets.trace.no_such_module"):
        load_target("targets.trace.no_such_module::f")


def test_load_target_names_a_function_the_module_lacks() -> None:
    with pytest.raises(TargetError, match="no_such_function"):
        load_target("targets.trace.uncalled_helper::no_such_function")


def test_load_target_names_a_module_with_no_python_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """A compiled extension module imports and has a ``__file__``, but no source to read.

    The module is built here rather than borrowed from the stdlib: which
    extensions ship as ``.so`` files differs by Python version and build.
    """
    module = types.ModuleType("fake_ext")
    module.__file__ = "/nowhere/fake_ext.cpython-312-darwin.so"
    setattr(module, "f", lambda x: x)  # noqa: B010 - a module built by hand
    monkeypatch.setitem(sys.modules, "fake_ext", module)
    with pytest.raises(TargetError, match="fake_ext has no Python source file"):
        load_target("fake_ext::f")


@pytest.mark.parametrize(
    ("module", "ending"),
    [
        pytest.param("targets.load.exits_at_import", "SystemExit(4)", id="exit-with-a-code"),
        pytest.param("targets.load.exits_cleanly_at_import", "SystemExit()", id="clean-exit"),
    ],
)
def test_load_target_names_an_exit_at_import_by_its_repr(module: str, ending: str) -> None:
    with pytest.raises(TargetError) as refused:
        load_target(f"{module}::f")

    assert str(refused.value) == f"cannot import {module}: {ending}"


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("targets.trace.uncalled_helper", id="imports"),
        pytest.param("targets.trace.broken_import", id="raises"),
    ],
)
def test_load_target_names_the_module_on_the_watch_while_it_imports(
    module: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = ImportWatch.for_command_line([f"{module}::classify"])
    named: list[str | None] = []
    real_import = importlib.import_module

    def import_module(name: str) -> ModuleType:
        named.append(watch.module())
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", import_module)

    with contextlib.suppress(TargetError):
        load_target(f"{module}::classify", watch)

    assert named == [module]
    assert watch.module() is None


def refused_as_python_refuses(spec: str) -> None:
    """``load_target`` refuses ``spec`` with the reason plain Python gives in this run.

    The reason is one line: the first line of Python's message that holds
    anything, or the exception's type name when none does.
    """
    with pytest.raises(TargetError) as refused:
        load_target(spec)

    module, name = spec.split("::")
    with pytest.raises(BaseException) as unread:
        inspect.signature(getattr(sys.modules[module], name))
    lines = [line for line in str(unread.value).splitlines() if line.strip()]
    reason = lines[0] if lines else type(unread.value).__name__
    assert str(refused.value) == f"cannot read the signature of {spec}: {reason}"


@pytest.mark.parametrize(
    "name",
    [
        "pick",
        "partial_max",
        "looped",
        "bad_signature",
        "wrong_signature_type",
        "builtin_alias",
        "odd_callable",
        "no_message",
        "two_line_message",
        "blank_first_line",
    ],
)
def test_load_target_refuses_a_target_whose_signature_python_cannot_read(name: str) -> None:
    refused_as_python_refuses(f"targets.load.unreadable_signatures::{name}")


@pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="before 3.14 the def evaluates its annotations, so the module does not import",
)
def test_load_target_refuses_an_annotation_python_cannot_evaluate() -> None:
    refused_as_python_refuses("targets.load.annotated_for_type_checking::f")
