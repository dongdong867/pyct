import contextlib
import functools
import importlib
import inspect
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

from pyct.binding.annotations import Fields, Items
from pyct.execution.execute import execute
from pyct.intercept.hook import Interception, current
from pyct.run.import_watch import ImportWatch
from pyct.run.target import (
    Target,
    TargetError,
    execution_context,
    interception,
    load_target,
)
from pyct.run.target import _self_class as self_class_of
from pyct.run.target import _self_name as self_name_of

REPO_ROOT = Path(__file__).resolve().parents[3]
CART = "targets.classes.cart"
SHOP = "targets.classes.shop"


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


def test_load_target_follows_a_dotted_name_one_attribute_at_a_time() -> None:
    target = load_target(f"{CART}::Outer.Inner.check")

    assert target.fn is sys.modules[CART].Outer.Inner.check
    assert target.file == str(REPO_ROOT / "targets" / "classes" / "cart.py")
    assert list(target.signature.parameters) == ["self", "x"]


@pytest.mark.parametrize(
    ("name", "parameters"),
    [
        pytest.param("Cart", ["owner"], id="a-class"),
        pytest.param("Cart.from_text", ["text"], id="a-classmethod"),
        pytest.param("Cart.rate", ["x"], id="a-staticmethod"),
        pytest.param("registry.lookup", ["key"], id="a-method-of-a-module-level-object"),
        pytest.param("handler", ["x"], id="a-callable-object"),
    ],
)
def test_load_target_reads_the_signature_of_what_the_name_ends_on(
    name: str, parameters: list[str]
) -> None:
    assert list(load_target(f"{CART}::{name}").signature.parameters) == parameters


@pytest.mark.parametrize(
    ("name", "self_class"),
    [
        pytest.param("Cart.total", "Cart", id="a-method"),
        pytest.param("Outer.Inner.check", "Outer.Inner", id="a-method-of-a-nested-class"),
        pytest.param("Cart.__repr__", "Cart", id="a-method-the-class-inherits"),
        pytest.param("Cart", None, id="a-class"),
        pytest.param("Outer.Inner", None, id="a-class-a-class-holds"),
        pytest.param("Cart.from_text", None, id="a-classmethod"),
        pytest.param("Cart.rate", None, id="a-staticmethod"),
        pytest.param("Cart.mro", None, id="a-method-of-the-class-s-own-type"),
        pytest.param("registry.lookup", None, id="a-method-of-a-module-level-object"),
        pytest.param("handler", None, id="a-callable-object"),
        pytest.param("Tags.fromkeys", None, id="a-classmethod-written-in-c"),
        pytest.param("Catalog.opened", None, id="a-descriptor-that-binds-to-the-class"),
    ],
)
def test_load_target_keeps_the_class_a_method_needs_an_instance_of_as_self(
    name: str, self_class: str | None
) -> None:
    target = load_target(f"{CART}::{name}")

    assert target.self_class is (
        None
        if self_class is None
        else functools.reduce(getattr, self_class.split("."), sys.modules[CART])
    )


@pytest.mark.parametrize(
    ("spec", "self_name"),
    [
        pytest.param(f"{SHOP}::Cart.total", "self", id="a-method"),
        pytest.param(f"{SHOP}::Till.total", "this", id="a-method-whose-first-parameter-is-this"),
        pytest.param(f"{CART}::Cart.from_text", None, id="a-classmethod"),
        pytest.param(f"{CART}::Cart", None, id="a-class"),
    ],
)
def test_load_target_names_self_by_the_method_s_first_parameter(
    spec: str, self_name: str | None
) -> None:
    assert load_target(spec).self_name == self_name


def test_load_target_reads_the_constructor_of_the_class_self_is_built_from() -> None:
    target = load_target(f"{SHOP}::Member.price")

    assert target.constructor is not None
    assert list(target.constructor.parameters) == ["name", "vip", "tags"]
    assert load_target(f"{CART}::Cart.from_text").constructor is None


def test_a_loaded_method_builds_self_by_the_constructor_s_own_signature() -> None:
    """The constructor's annotations resolve in its own module, not the method's, and its
    positional-only parameter goes by position."""
    ctx = execution_context(load_target("tests.unit.run.ledger::Ledger.total"))

    assert ctx.checks["self"] == Fields({"owner": str, "counts": Items(dict, int, keys=int)})
    assert ctx.self_build is not None
    assert [parameter.name for parameter in ctx.self_build.positional] == ["owner"]
    result = execute(ctx, {"self": {"owner": "admin", "counts": {"1": 2}}})
    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [
        ["==", ["[]", "self", "'owner'"], "'admin'"]
    ]


def _keyword_first(*, owner: str) -> None: ...


def _gathering_first(*args: object) -> None: ...


def _no_parameter() -> None: ...


@pytest.mark.parametrize(
    "method",
    [_keyword_first, _gathering_first, _no_parameter],
    ids=["keyword-only", "gathering", "none"],
)
def test_a_method_whose_first_parameter_takes_no_position_names_no_self(
    method: types.FunctionType,
) -> None:
    """Python passes the instance by position, so only such a parameter can take it (Q2)."""
    assert self_name_of(inspect.signature(method)) is None


class _Locked(type):
    """A type whose instances' type answers every attribute it lacks by raising."""

    def __getattr__(cls, name: str) -> object:
        raise RuntimeError(f"no {name}")


class _Binder(type):
    """A type whose own ``__get__`` makes its classes descriptors, not their instances."""

    def __get__(cls, instance: object, owner: type | None = None) -> object:
        return cls


@pytest.mark.parametrize("kind", [_Locked, _Binder], ids=["raises-on-a-read", "has-get"])
def test_a_callable_whose_type_s_own_type_reads_get_binds_to_nothing(kind: type) -> None:
    """Python looks ``__get__`` up along the held object's type, never on that type's type."""
    tool = kind("Tool", (), {"__call__": lambda self, x: x})()
    desk = type("Desk", (), {"tool": tool})

    assert self_class_of(desk, "tool", tool) is None


def test_an_object_on_the_path_is_told_from_a_class_without_reading_its_class_attribute() -> None:
    """``isinstance`` reads ``__class__``, which an object's own property can answer."""

    class Masked:
        @property
        def __class__(self) -> type:  # pyrefly: ignore[bad-override]
            raise RuntimeError("read __class__")

    masked = Masked()

    assert self_class_of(masked, "pick", len) is None


def test_a_classmethod_that_wraps_a_staticmethod_binds_to_nothing() -> None:
    """Python 3.12 reads such a chain through the class as the plain function it holds."""

    def f(x: int) -> int:
        return x

    chained = type("Chained", (), {"f": classmethod(staticmethod(f))})

    assert self_class_of(chained, "f", getattr(chained, "f")) is None  # noqa: B009


@pytest.mark.parametrize(
    "spec",
    [
        pytest.param(f"{CART}::Cart", id="a-class"),
        pytest.param(f"{CART}::Cart.total", id="a-method"),
        pytest.param(f"{CART}::Cart.from_text", id="a-classmethod"),
        pytest.param(f"{CART}::Cart.rate", id="a-staticmethod"),
        pytest.param(f"{CART}::Outer.Inner.check", id="a-method-of-a-nested-class"),
        pytest.param(f"{CART}::registry.lookup", id="a-method-of-a-module-level-object"),
        pytest.param(f"{CART}::handler", id="a-callable-object"),
        pytest.param(f"{CART}::Tags.fromkeys", id="a-classmethod-written-in-c"),
        pytest.param(f"{CART}::prices.get", id="a-method-written-in-c"),
        pytest.param(f"{CART}::store.till", id="a-property-on-the-path"),
        pytest.param(f"{CART}::Catalog.opened", id="a-descriptor-written-in-python"),
        pytest.param(f"{CART}::proxy.pick", id="an-object-that-looks-attributes-up-itself"),
        pytest.param("targets.classes.lazy::made", id="a-module-s-getattr"),
        pytest.param("targets.load.wrapped_at_top::cached", id="an-lru-cache"),
        pytest.param("targets.load.wrapped_at_top::cached_forever", id="a-cache"),
        pytest.param("targets.load.wrapped_at_top::logged", id="a-decorator-class-with-get"),
        pytest.param("targets.load.wrapped_at_top::partly", id="a-partial"),
    ],
)
def test_load_target_keeps_what_its_spec_reaches_as_found_by_that_name(spec: str) -> None:
    target = load_target(spec)

    assert target.followed == (spec, target.fn)


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Cart.totl", id="a-misspelled-method"),
        pytest.param("Cart.count", id="a-class-attribute"),
        pytest.param("Cart.size", id="a-property"),
        pytest.param("Outer.Missing.check", id="a-missing-name-before-the-last"),
    ],
)
def test_load_target_names_a_dotted_name_that_ends_on_no_function(name: str) -> None:
    with pytest.raises(TargetError) as refused:
        load_target(f"{CART}::{name}")

    assert str(refused.value) == f"{CART} has no function {name}"


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        pytest.param("shelf.fetch", "RuntimeError: the shelf is locked", id="a-runtime-error"),
        pytest.param("shelf.count", "ValueError: no stock", id="a-value-error"),
    ],
)
def test_load_target_names_a_read_along_the_name_that_raises_by_its_type_and_message(
    name: str, reason: str
) -> None:
    spec = f"targets.load.raises_on_the_path::{name}"

    with pytest.raises(TargetError) as refused:
        load_target(spec)

    assert str(refused.value) == f"cannot read {spec}: {reason}"


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


@pytest.mark.parametrize("alone", [True, False])
def test_an_execution_context_calls_the_target_as_its_signature_says(alone: bool) -> None:
    target = load_target("targets.sweep.defaults::g")

    context = execution_context(target, alone=alone)

    assert (context.fn, context.file, context.alone) == (target.fn, target.file, alone)
    assert [parameter.name for parameter in context.positional] == ["value"]
    assert list(context.checks) == ["strict"]
