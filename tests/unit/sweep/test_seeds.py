import enum
import inspect
import json
import typing
from collections.abc import Callable
from typing import Annotated, Literal, NewType, TypeVar

import pytest

from pyct.binding.annotations import contradictions
from pyct.binding.call import call_arguments, positional_only
from pyct.binding.resolve import checked_annotations
from pyct.sweep.seeds import NoSeedError, carried, seed_of
from targets.sweep import cannot_seed, defaults, seeds, seeds_as_text, text_annotations
from tests.unit.sweep import own_t

T = TypeVar("T")
UserId = NewType("UserId", int)


class Mode(enum.Enum):
    FAST = 1


class Level(enum.IntEnum):
    LOW = 1


class Widget:
    pass


EVERY_KIND = {"a": 0, "b": 0.0, "c": "", "d": False, "e": [], "g": {}, "h": 0, "i": ""}
EVERY_KIND |= {"j": [], "k": "x", "m": None, "n": 0, "p": 0}
DEFAULTS = {"x": 0, "strict": False, "sep": ",", "ratio": 0.5, "tags": ["a"]}


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


def reason(fn: Callable[..., object]) -> str:
    with pytest.raises(NoSeedError) as raised:
        seed_of(fn)
    return str(raised.value)


def test_a_parameter_with_no_default_gets_the_first_value_its_annotation_accepts() -> None:
    assert as_json(seed_of(seeds.f)) == as_json(EVERY_KIND)


def test_text_annotations_give_the_same_seed() -> None:
    assert as_json(seed_of(seeds_as_text.f)) == as_json(EVERY_KIND)


def test_a_default_json_carries_stays_and_any_other_is_left_out() -> None:
    assert as_json(seed_of(defaults.f)) == as_json(DEFAULTS)


def test_a_default_is_checked_against_a_text_annotation() -> None:
    assert as_json(seed_of(seeds_as_text.with_defaults)) == as_json(DEFAULTS)


def test_a_positional_only_and_a_keyword_only_parameter_are_both_named() -> None:
    assert as_json(seed_of(defaults.g)) == as_json({"value": 0, "strict": False})


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        pytest.param(Annotated[int, "meta"], 0, id="annotated"),
        pytest.param(Annotated[Literal["b"], "meta"], "b", id="annotated literal"),
        # a Literal in a union gives its first value, before any other member is tested
        pytest.param(Literal["b", "c"] | None, "b", id="literal in a union"),
        pytest.param(typing.Optional[Literal["a", "b"]], "a", id="optional literal"),  # noqa: UP045
        pytest.param(int | Literal["x"], "x", id="literal after another member"),
        pytest.param(
            Annotated[Literal["d"], "meta"] | None, "d", id="annotated literal in a union"
        ),
        # a value JSON cannot carry gives way to the other members
        pytest.param(Literal[b"x"] | None, None, id="literal JSON cannot carry in a union"),
        pytest.param(typing.Optional[list[int]], [], id="optional list"),  # noqa: UP045
        pytest.param(Annotated[str, "meta"] | None, "", id="annotated in a union"),
        pytest.param(float, 0.0, id="float"),
        pytest.param(object, 0, id="object"),
        pytest.param(type(None), None, id="NoneType"),
        pytest.param(T, 0, id="type variable"),
        pytest.param(UserId, 0, id="new type"),
        pytest.param("Undefined", 0, id="text no module resolves"),
    ],
)
def test_the_value_for_one_annotation(annotation: object, value: object) -> None:
    def target(v) -> None:
        return None

    target.__annotations__ = {"v": annotation}
    assert as_json(seed_of(target)) == as_json({"v": value})


def test_a_list_value_is_a_fresh_list_each_time() -> None:
    first = seed_of(seeds.f)
    typing.cast(list, first["e"]).append(1)
    assert seed_of(seeds.f)["e"] == []


@pytest.mark.parametrize(
    ("annotation", "written"),
    [
        pytest.param(bytes, "bytes", id="bytes"),
        pytest.param(tuple[int, int], "tuple[int, int]", id="tuple"),
        pytest.param(Mode, f"{__name__}.Mode", id="enum"),
        pytest.param(Widget, f"{__name__}.Widget", id="class"),
        pytest.param(Literal[b"x"], "Literal[b'x']", id="literal JSON cannot carry"),
    ],
)
def test_no_value_fits(annotation: object, written: str) -> None:
    def target(v) -> None:
        return None

    target.__annotations__ = {"v": annotation}
    assert reason(target) == f"no seed for v: {written}"


def test_a_text_annotation_is_written_as_the_signature_prints_it() -> None:
    assert reason(seeds_as_text.load) == "no seed for data: 'bytes'"


@pytest.mark.parametrize("fn", [own_t.first, own_t.Child])
def test_text_two_modules_read_as_different_objects_agrees_on_the_value(
    fn: Callable[..., object],
) -> None:
    # each module builds its own list[T]; both give [], and pyct run asks for a list
    assert seed_of(fn) == {"items": []}


def test_an_unresolved_text_annotation_gets_zero() -> None:
    assert as_json(seed_of(text_annotations.f)) == as_json({"a": 0, "b": [], "c": 0})


@pytest.mark.parametrize("fn", [cannot_seed.main, cannot_seed.only, cannot_seed.later])
def test_nothing_to_vary(fn: Callable[..., object]) -> None:
    assert reason(fn) == "no parameter to vary"


def test_a_signature_python_cannot_read() -> None:
    with pytest.raises(TypeError) as plain:
        inspect.signature(cannot_seed.odd)
    assert reason(cannot_seed.odd) == f"cannot read the signature: {plain.value}"


def test_a_class_is_seeded_at_its_constructor() -> None:
    class Cart:
        def __init__(self, owner: str, limit: int = 3) -> None:
            self.owner = owner

    assert seed_of(Cart) == {"owner": "", "limit": 3}


@pytest.mark.parametrize(
    "value",
    [None, True, 1, 1.5, "a", [1, [2.5, None]], {"a": {"b": [True]}}],
)
def test_json_carries(value: object) -> None:
    assert carried(value)


def _holds_itself() -> list[object]:
    items: list[object] = []
    items.append(items)
    return items


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"),
        pytest.param((1, 2), id="tuple"),
        pytest.param({1: "a"}, id="int key"),
        pytest.param(Level.LOW, id="int subclass"),
        pytest.param([b"x"], id="bytes inside"),
        pytest.param(_holds_itself(), id="holds itself"),
    ],
)
def test_json_does_not_carry(value: object) -> None:
    assert not carried(value)


@pytest.mark.parametrize(
    "fn",
    [
        seeds.f,
        defaults.f,
        defaults.g,
        seeds_as_text.f,
        seeds_as_text.with_defaults,
        own_t.first,
        own_t.Child,
    ],
)
def test_every_seed_passes_pyct_runs_seed_checks(fn: Callable[..., object]) -> None:
    seed = seed_of(fn)
    signature = inspect.signature(fn)

    assert contradictions(checked_annotations(signature, fn), seed) == []
    positional, keywords = call_arguments(positional_only(signature), seed)
    signature.bind(*positional, **keywords)
