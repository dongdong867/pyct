import importlib
import inspect
import json

import pytest

from pyct.run.seed_checks import SeedCheck
from pyct.run.target import load_target
from pyct.sweep.seeds import NoSeedError, method_seed
from targets.sweep import methods, orders

# what sweep seeds targets.sweep.orders.Order with
ORDER = {"id": 0, "items": []}


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


def method_reason(cls: type, name: str) -> str:
    with pytest.raises(NoSeedError) as raised:
        method_seed(cls, name)
    return str(raised.value)


# sweep-method-entry
def test_a_method_seed_holds_the_constructor_seed_under_self() -> None:
    expected = {"self": ORDER, "discount": 0, "strict": False}
    assert as_json(method_seed(orders.Order, "total")) == as_json(expected)


# sweep-method-entry
def test_a_method_seed_writes_its_defaults() -> None:
    class Ruler:
        def __init__(self, unit: str = "cm") -> None:
            self.unit = unit

        def measure(self, length: float, rounded: bool = True, places: int = 2) -> str:
            return f"{length}{self.unit}"

    expected = {"self": {"unit": "cm"}, "length": 0.0, "rounded": True, "places": 2}
    assert as_json(method_seed(Ruler, "measure")) == as_json(expected)


# sweep-method-entry
@pytest.mark.parametrize(
    ("name", "seed"),
    [
        pytest.param("count", {"items": []}, id="a static method"),
        pytest.param("blank", {"id": 0}, id="a class method"),
    ],
)
def test_a_static_and_a_class_method_seed_holds_only_its_own_parameters(
    name: str, seed: dict[str, object]
) -> None:
    assert as_json(method_seed(orders.Order, name)) == as_json(seed)


# sweep-method-entry
def test_a_method_s_object_is_keyed_by_its_first_parameter() -> None:
    class Odd:
        def __init__(self, n: int) -> None:
            self.n = n

        def scaled(this, by: int) -> int:  # noqa: N805 - a first parameter not named self
            return this.n * by

        def spread(*args: int) -> int:  # noqa: N805 - a first parameter that takes no position
            return len(args)

    assert as_json(method_seed(Odd, "scaled")) == as_json({"this": {"n": 0}, "by": 0})
    with pytest.raises(NoSeedError, match="^no parameter to vary$"):
        method_seed(Odd, "spread")


# sweep-method-unbuildable
def test_a_method_whose_object_sweep_cannot_seed_is_skipped() -> None:
    class Unread:
        def __init__(self, n: int) -> None:
            self.n = n

        def show(self, width: int) -> str:
            return str(self.n).rjust(width)

    Unread.__signature__ = 5  # pyrefly: ignore[missing-attribute]
    with pytest.raises(TypeError) as plain:
        inspect.signature(Unread)

    written = "no seed for self: no seed for key: collections.abc.Callable[[int], int]"
    assert method_reason(orders.Keyed, "run") == written
    assert (
        method_reason(Unread, "show")
        == f"no seed for self: cannot read the signature: {plain.value}"
    )


# sweep-method-unbuildable
@pytest.mark.parametrize(
    ("cls", "name"),
    [
        pytest.param(orders.Tag, "name", id="an object with nothing to build"),
        pytest.param(methods.Cart, "empty", id="a class method with no parameter"),
    ],
)
def test_a_method_that_varies_nothing_is_skipped(cls: type, name: str) -> None:
    assert method_reason(cls, name) == "no parameter to vary"


# sweep-method-entry
@pytest.mark.parametrize(
    "spec",
    [
        "targets.sweep.orders::Order.total",
        "targets.sweep.orders::Order.count",
        "targets.sweep.orders::Order.blank",
        "targets.sweep.orders::Customer.owes",
        "targets.sweep.methods::Parser.parse",
    ],
)
def test_every_method_seed_passes_pyct_run_s_seed_check(spec: str) -> None:
    module, _, name = spec.partition("::")
    owner, _, method = name.partition(".")
    target = load_target(spec, keep_import_lines=False)
    seed = method_seed(getattr(importlib.import_module(module), owner), method)

    assert SeedCheck.of(target).read(json.dumps(seed)) == (seed, [])
