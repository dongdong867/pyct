import contextlib
import importlib
import inspect
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

from pyct.intercept.hook import Interception, current
from pyct.run.import_watch import ImportWatch
from pyct.run.target import Target, TargetError, interception, load_target

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_target_imports_from_the_current_directory() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    assert isinstance(target, Target)
    assert target.spec == "targets.trace.uncalled_helper::classify"
    assert target.file == str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
    assert list(target.signature.parameters) == ["x"]
    assert target.fn(x=1) == "small"


def test_load_target_keeps_the_lines_its_import_of_the_module_ran() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    # the docstring and both defs; no function's body
    assert target.import_lines == frozenset({1, 4, 10})


def test_load_target_keeps_no_import_lines_when_told_not_to() -> None:
    target = load_target("targets.trace.uncalled_helper::classify", keep_import_lines=False)

    assert target.import_lines == frozenset()


def test_load_target_keeps_no_line_of_a_module_already_imported() -> None:
    load_target("targets.trace.uncalled_helper::classify")

    assert load_target("targets.trace.uncalled_helper::classify").import_lines == frozenset()


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
    """``load_target`` refuses ``spec`` with the message plain Python gives in this run.

    For inspect's own refusals, whose words CPython changes between
    versions; each is one line.
    """
    with pytest.raises(TargetError) as refused:
        load_target(spec)

    module, name = spec.split("::")
    with pytest.raises((ValueError, TypeError)) as unread:
        inspect.signature(getattr(sys.modules[module], name))
    assert str(refused.value) == f"cannot read the signature of {spec}: {unread.value}"


@pytest.mark.parametrize(
    "name",
    ["pick", "partial_max", "looped", "bad_signature", "wrong_signature_type", "builtin_alias"],
)
def test_load_target_refuses_a_target_whose_signature_python_cannot_read(name: str) -> None:
    refused_as_python_refuses(f"targets.load.unreadable_signatures::{name}")


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        pytest.param("odd_callable", "KeyError: '__wrapped__'", id="a-bare-key"),
        pytest.param("no_message", "RuntimeError", id="no-message"),
        pytest.param("two_line_message", "first line", id="two-lines"),
        pytest.param("blank_first_line", "after a blank line", id="a-blank-first-line"),
        pytest.param("exits_while_read", "SystemExit: 0", id="an-exit"),
        pytest.param("unprintable", "UnprintableError", id="a-message-that-raises"),
        pytest.param(
            "subclass_of_value_error", "UnicodeError: bad text", id="a-subclass-of-value-error"
        ),
    ],
)
def test_load_target_gives_one_line_that_is_never_empty(name: str, reason: str) -> None:
    spec = f"targets.load.unreadable_signatures::{name}"

    with pytest.raises(TargetError) as refused:
        load_target(spec)

    assert str(refused.value) == f"cannot read the signature of {spec}: {reason}"


@pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="before 3.14 the def evaluates its annotations, so the module does not import",
)
def test_load_target_refuses_an_annotation_python_cannot_evaluate() -> None:
    spec = "targets.load.annotated_for_type_checking::f"

    with pytest.raises(TargetError) as refused:
        load_target(spec)

    # not one of inspect's own refusals, so the reason names the exception's type
    with pytest.raises(NameError) as unread:
        inspect.signature(sys.modules["targets.load.annotated_for_type_checking"].f)
    reason = f"NameError: {unread.value}"
    assert str(refused.value) == f"cannot read the signature of {spec}: {reason}"


def test_the_interception_of_a_spec_substitutes_its_module_s_package_into_the_cache_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))

    with interception("shop.cart::total"):
        held = current()

    assert held == Interception(module="shop.cart", cache=tmp_path)
    assert current() is None
