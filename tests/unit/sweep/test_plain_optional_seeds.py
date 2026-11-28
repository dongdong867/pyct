import importlib
import json
from collections.abc import Callable
from typing import Literal, Optional, TypeVar

import pytest

from pyct.run.seed_checks import SeedCheck
from pyct.run.target import load_target
from pyct.sweep.seeds import first_seed, method_seeds, seeds_of
from targets.sweep import defaults, optional, orders

# what sweep seeds targets.sweep.orders.Order with
ORDER = {"id": 0, "items": []}

T = TypeVar("T")


def written(seeds: list[dict[str, object]]) -> list[str]:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return [json.dumps(seed) for seed in seeds]


def none_default(annotation: object, default: object = None) -> Callable[..., object]:
    """A function of one parameter, ``v``, hinted with ``annotation``, with ``default``."""

    def target(v=default) -> None:
        return None

    target.__annotations__ = {"v": annotation}
    return target


def no_default(annotation: object) -> Callable[..., object]:
    """A function of one parameter, ``v``, hinted with ``annotation``, with no default."""

    def target(v) -> None:
        return None

    target.__annotations__ = {"v": annotation}
    return target


def limited(x: int, limit: int = None) -> None:  # type: ignore[assignment]  # noqa: RUF013
    return None


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    ("fn", "expected"),
    [
        pytest.param(
            optional.lang_filter,
            [{"url": "", "language": None}, {"url": "", "language": ""}],
            id="a str beside None",
        ),
        pytest.param(
            optional.make_time,
            [{"frames": None, "fps": None}, {"frames": 0, "fps": 0.0}],
            id="several in one entry change together",
        ),
        pytest.param(
            none_default(Optional[int]),  # noqa: UP045
            [{"v": None}, {"v": 0}],
            id="typing.Optional",
        ),
        pytest.param(none_default("str | None"), [{"v": None}, {"v": ""}], id="a text annotation"),
        pytest.param(
            none_default(Literal["a", "b"] | None),
            [{"v": None}, {"v": "a"}],
            id="a Literal beside None",
        ),
    ],
)
def test_a_plain_type_beside_none_gives_a_second_seed_with_its_value(
    fn: Callable[..., object], expected: list[dict[str, object]]
) -> None:
    assert written(seeds_of(fn)) == written(expected)


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    ("seeds", "expected"),
    [
        pytest.param(
            seeds_of(optional.Filter),
            [{"language": None}, {"language": ""}],
            id="a constructor's parameter",
        ),
        pytest.param(
            method_seeds(optional.Filter, "keep"),
            [{"self": {"language": None}, "url": ""}, {"self": {"language": ""}, "url": ""}],
            id="a method's constructor",
        ),
        pytest.param(
            seeds_of(optional.screen),
            [{"rule": {"language": None}}, {"rule": {"language": ""}}],
            id="a class a hint builds",
        ),
    ],
)
def test_a_plain_optional_is_built_at_every_depth(
    seeds: list[dict[str, object]], expected: list[dict[str, object]]
) -> None:
    assert written(seeds) == written(expected)


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    "fn",
    [
        pytest.param(none_default(bytes | None), id="no plain value fits"),
        pytest.param(none_default(None), id="None alone"),
        pytest.param(none_default(T | None), id="a hint isinstance cannot test"),
        pytest.param(no_default(str | None), id="no default"),
        pytest.param(none_default(str | None, "x"), id="a default other than None"),
    ],
)
def test_one_seed_when_no_plain_value_differs(fn: Callable[..., object]) -> None:
    assert written(seeds_of(fn)) == written([first_seed(fn)])


# sweep-none-default-class-seeds
def test_a_none_default_on_a_plain_hint_gives_a_second_seed_with_its_value() -> None:
    assert written(seeds_of(limited)) == written([{"x": 0}, {"x": 0, "limit": 0}])
    first = {"x": 0, "strict": False, "sep": ",", "ratio": 0.5, "tags": ["a"]}
    assert written(seeds_of(defaults.f)) == written([first, {**first, "limit": 0}])


# sweep-none-default-class-seeds
def test_a_class_in_the_hint_comes_before_its_plain_types() -> None:
    built = none_default(orders.Order | str | None)
    unbuilt = none_default(orders.Keyed | int | None)

    assert written(seeds_of(built)) == written([{"v": None}, {"v": ORDER}])
    assert written(seeds_of(unbuilt)) == written([{"v": None}, {"v": 0}])


# sweep-none-default-class-seeds
@pytest.mark.parametrize(
    "spec",
    [
        "targets.sweep.optional::lang_filter",
        "targets.sweep.optional::make_time",
        "targets.sweep.optional::Filter",
        "targets.sweep.optional::Filter.keep",
        "targets.sweep.optional::screen",
    ],
)
def test_every_plain_optional_second_seed_passes_pyct_run_s_seed_check(spec: str) -> None:
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
