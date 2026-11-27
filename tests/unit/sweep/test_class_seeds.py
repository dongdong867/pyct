import abc
import enum
import fractions
import importlib
import json
from collections.abc import Callable
from typing import Protocol

import pytest

from pyct.run.seed_checks import SeedCheck
from pyct.run.target import load_target
from pyct.sweep.seeds import NoSeedError, method_seeds, seed_of, seeds_of
from targets.sweep import nodes, orders
from tests.unit.sweep import later_named

# what sweep seeds targets.sweep.orders.Order with
ORDER = {"id": 0, "items": []}


class Mode(enum.Enum):
    FAST = 1


class Widget:
    pass


class Pair(enum.Enum):
    BOTH = (1, 2)


class Empty(enum.Enum):
    pass


class Shaped(Protocol):
    def area(self) -> float: ...


class Shape(abc.ABC):
    @abc.abstractmethod
    def area(self) -> float: ...


class Pocket:
    def __init__(self, coin: int = 0) -> None:
        self.coin = coin


class Purse:
    def __init__(self, pocket: Pocket | None = None, order: orders.Order | None = None) -> None:
        self.pocket = pocket


def hold(purse: Purse | None = None, spare: Pocket | None = None) -> None:
    return None


def hold_two(order: orders.Order | None = None, keyed: orders.Keyed | None = None) -> None:
    return None


def bare(order: orders.Order = None) -> None:  # type: ignore[assignment]  # noqa: RUF013
    return None


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


def reason(fn: Callable[..., object]) -> str:
    with pytest.raises(NoSeedError) as raised:
        seed_of(fn)
    return str(raised.value)


def hinted(annotation: object) -> Callable[..., object]:
    """A function of one parameter, ``v``, hinted with ``annotation``."""

    def target(v) -> None:
        return None

    target.__annotations__ = {"v": annotation}
    return target


# sweep-class-hint-seed
@pytest.mark.parametrize(
    ("fn", "seed"),
    [
        pytest.param(orders.ship, {"order": ORDER}, id="a class with a constructor"),
        pytest.param(hinted(Widget), {"v": {}}, id="a class with no constructor"),
        pytest.param(hinted(Mode), {"v": [1]}, id="an enum class, its first member's value"),
        pytest.param(later_named.Placed, {"owner": {}}, id="a postponed class hint"),
    ],
)
def test_a_class_hint_gets_its_constructor_seed(
    fn: Callable[..., object], seed: dict[str, object]
) -> None:
    assert as_json(seed_of(fn)) == as_json(seed)


# sweep-class-hint-seed
def test_a_class_seed_nests_level_by_level() -> None:
    expected = {"customer": {"name": "", "order": ORDER}}
    assert as_json(seed_of(orders.bill)) == as_json(expected)


# sweep-class-hint-seed
def test_a_class_with_no_python_constructor_or_no_parameter_gives_an_empty_object() -> None:
    assert as_json(seed_of(orders.label)) == as_json({"tag": {}, "stamp": {}})


# sweep-class-hint-seed
@pytest.mark.parametrize(
    ("fn", "written"),
    [
        pytest.param(
            orders.apply,
            "no seed for keyed: no seed for key: collections.abc.Callable[[int], int]",
            id="a class whose constructor sweep cannot seed",
        ),
        pytest.param(
            hinted(Pair),
            "no seed for v: the first member of Pair has a value JSON cannot carry",
            id="an enum class whose first value JSON cannot carry",
        ),
        pytest.param(hinted(Empty), "no seed for v: Empty has no member", id="an empty enum class"),
    ],
)
def test_a_class_sweep_cannot_seed_skips_with_its_constructor_s_reason(
    fn: Callable[..., object], written: str
) -> None:
    assert reason(fn) == written


# sweep-class-hint-seed
def test_a_class_its_own_seed_needs_again_skips() -> None:
    assert reason(nodes.Node) == "no seed for next: Node needs a Node to build"
    assert reason(nodes.follow) == "no seed for head: no seed for next: Node needs a Node to build"


# sweep-none-default-class-seeds
def test_a_class_beside_none_with_no_default_gives_null_then_the_object() -> None:
    assert as_json(seed_of(orders.maybe)) == as_json({"order": None})
    assert [as_json(seed) for seed in seeds_of(orders.maybe)] == [
        as_json({"order": None}),
        as_json({"order": ORDER}),
    ]


# sweep-optional-class-seed
@pytest.mark.parametrize(
    ("fn", "seed"),
    [
        pytest.param(orders.maybe_apply, {"keyed": None}, id="a class beside None"),
        pytest.param(orders.hooked, {"hook": {"keyed": None}}, id="in a class's constructor"),
    ],
)
def test_a_class_beside_none_sweep_cannot_seed_gets_today_s_value(
    fn: Callable[..., object], seed: dict[str, object]
) -> None:
    assert as_json(seed_of(fn)) == as_json(seed)


# sweep-optional-class-seed
def test_a_class_beside_none_needed_again_stops_at_null() -> None:
    assert as_json(seed_of(nodes.walk)) == as_json({"head": {"next": None}})
    assert as_json(seed_of(nodes.Link)) == as_json({"next": None})


# sweep-class-hint-seed
@pytest.mark.parametrize(
    ("annotation", "outcome"),
    [
        pytest.param(fractions.Fraction, "fractions.Fraction", id="a library's class"),
        pytest.param(Shaped, {"v": 0}, id="a Protocol class"),
        pytest.param(Shape, f"{__name__}.Shape", id="an abstract class"),
        pytest.param(
            orders.Order | orders.Customer,
            "targets.sweep.orders.Order | targets.sweep.orders.Customer",
            id="a union of two classes",
        ),
    ],
)
def test_a_hint_run_does_not_build_keeps_today_s_seed(annotation: object, outcome: object) -> None:
    target = hinted(annotation)
    if isinstance(outcome, str):
        assert reason(target) == f"no seed for v: {outcome}"
    else:
        assert as_json(seed_of(target)) == as_json(outcome)


# sweep-class-hint-seed, sweep-optional-class-seed
@pytest.mark.parametrize(
    "spec",
    [
        "targets.sweep.orders::ship",
        "targets.sweep.orders::maybe",
        "targets.sweep.orders::bill",
        "targets.sweep.orders::maybe_apply",
        "targets.sweep.orders::hooked",
        "targets.sweep.orders::label",
        "targets.sweep.orders::pick",
        "targets.sweep.orders::Customer",
        "targets.sweep.nodes::walk",
        "targets.sweep.nodes::Link",
    ],
)
def test_every_class_seed_passes_pyct_run_s_seed_check(spec: str) -> None:
    target = load_target(spec, keep_import_lines=False)
    seed = seed_of(target.fn)

    assert SeedCheck.of(target).read(json.dumps(seed)) == (seed, [])


def written(seeds: list[dict[str, object]]) -> list[str]:
    return [as_json(seed) for seed in seeds]


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    ("seeds", "expected"),
    [
        pytest.param(
            seeds_of(orders.later),
            [{"order": None}, {"order": ORDER}],
            id="a class beside None, default None",
        ),
        pytest.param(
            seeds_of(bare), [{"order": None}, {"order": ORDER}], id="a bare class, default None"
        ),
        pytest.param(
            seeds_of(orders.Basket),
            [{"order": None}, {"order": ORDER}],
            id="a constructor's parameter",
        ),
        pytest.param(
            method_seeds(orders.Basket, "weigh"),
            [{"self": {"order": None}, "n": 0}, {"self": {"order": ORDER}, "n": 0}],
            id="a method's constructor",
        ),
    ],
)
def test_a_none_default_class_gives_a_second_seed_with_it_built(
    seeds: list[dict[str, object]], expected: list[dict[str, object]]
) -> None:
    assert written(seeds) == written(expected)


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    "fn",
    [
        pytest.param(orders.ship, id="no None default"),
        pytest.param(orders.maybe_apply, id="a class sweep cannot seed"),
        pytest.param(nodes.walk, id="a class that needs itself"),
        pytest.param(hinted(int | None), id="plain types beside None"),
    ],
)
def test_one_seed_when_the_second_equals_the_first(fn: Callable[..., object]) -> None:
    assert written(seeds_of(fn)) == [as_json(seed_of(fn))]


# sweep-none-default-class-seeds
def test_a_second_seed_builds_every_such_parameter_at_every_depth() -> None:
    first = {"purse": None, "spare": None}
    purse = {"pocket": {"coin": 0}, "order": ORDER}
    second = {"purse": purse, "spare": {"coin": 0}}
    assert written(seeds_of(hold)) == written([first, second])


# sweep-none-default-class-seeds
def test_a_second_seed_keeps_null_for_a_class_sweep_cannot_seed_or_that_needs_itself() -> None:
    first = {"order": None, "keyed": None}
    assert written(seeds_of(hold_two)) == written([first, {"order": ORDER, "keyed": None}])
    assert written(seeds_of(nodes.walk_chain)) == written(
        [{"head": None}, {"head": {"next": None}}]
    )


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    "spec",
    [
        "targets.sweep.orders::later",
        "targets.sweep.orders::maybe",
        "targets.sweep.orders::Basket",
        "targets.sweep.orders::Basket.weigh",
        "targets.sweep.nodes::walk_chain",
        "targets.sweep.nodes::Chain",
    ],
)
def test_every_second_seed_passes_pyct_run_s_seed_check(spec: str) -> None:
    target = load_target(spec, keep_import_lines=False)
    module, _, name = spec.partition("::")
    owner, _, method = name.partition(".")
    if method:
        seeds = method_seeds(getattr(importlib.import_module(module), owner), method)
    else:
        seeds = seeds_of(target.fn)

    assert len(seeds) == 2
    for seed in seeds:
        assert SeedCheck.of(target).read(json.dumps(seed)) == (seed, [])
