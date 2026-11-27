import abc
import enum
import fractions
import importlib
import inspect
import json
import math
import typing
from collections.abc import Callable
from typing import Annotated, Literal, NewType, Protocol, TypeVar

import pytest

from pyct.binding.annotations import contradictions
from pyct.binding.call import call_arguments, positional_only
from pyct.binding.resolve import checked_annotations
from pyct.binding.seed_keys import read_key
from pyct.run.seed_checks import SeedCheck
from pyct.run.target import load_target
from pyct.sweep.seeds import NoSeedError, carried, method_seed, seed_of
from targets.sweep import (
    cannot_seed,
    defaults,
    methods,
    nodes,
    orders,
    seeds,
    seeds_as_text,
    text_annotations,
)
from tests.unit.sweep import later_named, own_t

T = TypeVar("T")
UserId = NewType("UserId", int)


class Mode(enum.Enum):
    FAST = 1


class Level(enum.IntEnum):
    LOW = 1


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


EVERY_KIND = {"a": 0, "b": 0.0, "c": "", "d": False, "e": [], "g": {}, "h": 0, "i": ""}
EVERY_KIND |= {"j": [], "k": "x", "m": None, "n": 0, "p": 0}
DEFAULTS = {"x": 0, "strict": False, "sep": ",", "ratio": 0.5, "tags": ["a"]}

# default dicts that hold the key that names an object form, at the top and further in
CLASS_KEYED = {"__class__": "plain", "n": 1}
CLASS_KEYED_IN_A_LIST = [CLASS_KEYED]
CLASS_KEYED_IN_A_DICT = {"inner": {"__class__": "plain", "n": 1}}
# a default dict whose keys are already ! then __class__
BANGED = {"!__class__": 1, "!!__class__": 2, "n": 3}
# what sweep seeds targets.sweep.orders.Order with
ORDER = {"id": 0, "items": []}

# defaults whose keys are other dunder names, a ! key, and a str value "__class__"
OTHER_KEYS = {"__complex__": True, "!x": [{"__args__": "__class__"}], "__class__x": 0}
OTHER_ROWS = [OTHER_KEYS, "__class__"]


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


def test_a_parameter_with_no_default_gets_the_first_value_its_annotation_accepts() -> None:
    assert as_json(seed_of(seeds.f)) == as_json(EVERY_KIND)


def test_text_annotations_give_the_same_seed() -> None:
    assert as_json(seed_of(seeds_as_text.f)) == as_json(EVERY_KIND)


def test_a_default_json_carries_stays_and_any_other_is_left_out() -> None:
    assert as_json(seed_of(defaults.f)) == as_json(DEFAULTS)


def test_a_default_is_checked_against_a_text_annotation() -> None:
    assert as_json(seed_of(seeds_as_text.with_defaults)) == as_json(DEFAULTS)


def test_a_default_that_is_no_finite_float_stays_as_pythons_json_writes_it() -> None:
    def bounded(x, low=-math.inf, high=math.inf, missing=math.nan) -> None:
        return None

    written = '{"x": 0, "low": -Infinity, "high": Infinity, "missing": NaN}'
    assert as_json(seed_of(bounded)) == written


def test_a_default_dict_writes_its_class_key_escaped_at_any_depth() -> None:
    def held(d=CLASS_KEYED, rows=CLASS_KEYED_IN_A_LIST, nested=CLASS_KEYED_IN_A_DICT) -> None:
        return None

    written = {"!__class__": "plain", "n": 1}
    expected = {"d": written, "rows": [written], "nested": {"inner": written}}
    assert as_json(seed_of(held)) == as_json(expected)


def test_a_default_key_of_bangs_then_class_takes_one_bang_more() -> None:
    def held(d=BANGED) -> None:
        return None

    written = seed_of(held)["d"]

    assert as_json(written) == as_json({"!!__class__": 1, "!!!__class__": 2, "n": 3})
    assert isinstance(written, dict)
    assert {read_key(key): value for key, value in written.items()} == BANGED


def test_escaping_leaves_the_default_itself_as_it_was() -> None:
    def held(d=CLASS_KEYED_IN_A_DICT) -> None:
        return None

    seed_of(held)

    assert as_json(CLASS_KEYED_IN_A_DICT) == as_json({"inner": {"__class__": "plain", "n": 1}})


def test_a_default_with_no_class_key_is_written_as_it_is() -> None:
    def held(d=OTHER_KEYS, rows=OTHER_ROWS) -> None:
        return None

    assert as_json(seed_of(held)) == as_json({"d": OTHER_KEYS, "rows": OTHER_ROWS})


def test_a_positional_only_and_a_keyword_only_parameter_are_both_named() -> None:
    assert as_json(seed_of(defaults.g)) == as_json({"value": 0, "strict": False})


def test_an_annotated_star_args_and_star_kwargs_are_never_named() -> None:
    def spread(first: str, *items: int, **named: int) -> None:
        return None

    assert as_json(seed_of(spread)) == as_json({"first": ""})


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
    [
        None,
        True,
        1,
        1.5,
        float("inf"),
        float("-inf"),
        float("nan"),
        "a",
        [1, [2.5, None]],
        {"a": {"b": [True]}},
    ],
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


def test_a_named_tuple_s_postponed_hints_are_read_as_text() -> None:
    assert as_json(seed_of(later_named.Label)) == as_json({"text": "", "size": 0})


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


# sweep-optional-class-seed
def test_a_class_beside_none_gets_its_constructor_seed() -> None:
    assert as_json(seed_of(orders.maybe)) == as_json({"order": ORDER})


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
