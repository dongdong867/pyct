import collections.abc
import datetime
import functools
import inspect
import operator
import typing
from typing import Any, Optional, TypedDict

import pytest

from pyct.binding.annotations import Builds, Check, Fields, Items, NoOneClass
from pyct.binding.hints import Inside, hint_check, inside_of
from pyct.binding.resolve import checked_annotations
from tests.unit.binding.hint_classes import (
    Abstract,
    Box,
    Drawable,
    Line,
    Node,
    Pair,
    Rows,
    Shape,
    Spot,
)
from tests.unit.binding.hint_elsewhere import Split
from tests.unit.binding.named_classes import Point

NAME_IT = 'name the class to build with "__class__"'


class Spec(TypedDict):
    size: int


class Raising(type):
    """A metaclass whose subclass test raises, as a class's own code can."""

    def __subclasscheck__(cls, other: type) -> bool:
        raise RuntimeError("no test")


class Odd(metaclass=Raising):
    pass


@pytest.mark.parametrize(
    ("hint", "built"),
    [
        (Point, Point),
        (Spot, Spot),
        (Pair, Pair),
        (datetime.date, datetime.date),
        (Box[int], Box),
        (Point | None, Point),
        (Optional[Point], Point),  # noqa: UP045 - the old spelling is what it reads
        (Point | str, Point),
        (int | Point | None, Point),
    ],
)
def test_a_hint_that_names_one_class_builds_it(hint: object, built: type) -> None:
    assert hint_check(hint) == Builds(built)


@pytest.mark.parametrize(
    ("hint", "kept"),
    [
        (dict, Items(dict, None)),
        (list, Items(list, None)),
        (list[int], Items(list, int)),
        (dict[int, Point], Items(dict, None, keys=int)),
        (int, int),
        (tuple, None),
        (tuple[Point, Point], None),
        (typing.Sequence[Point], None),  # noqa: UP006 - the old spelling is what it reads
        (collections.abc.Mapping[str, Point], None),
        (collections.abc.Iterable, None),
        (object, None),
        (Any, None),
        (Spec, None),
        (Rows, None),
        (set, None),
        (Point | list[int], None),
        (Point | Spec, None),
        (int | None, None),
        (str | int, None),
    ],
)
def test_a_hint_that_names_no_class_to_build_reads_as_before(
    hint: object, kept: Check | None
) -> None:
    assert hint_check(hint) == kept


@pytest.mark.parametrize(
    ("hint", "reason"),
    [
        (Shape, f"hint Shape is an abstract class; {NAME_IT}"),
        (Shape | None, f"hint Shape is an abstract class; {NAME_IT}"),
        (Drawable, f"hint Drawable is a Protocol; {NAME_IT}"),
        (Abstract, f"hint Abstract is a Protocol; {NAME_IT}"),
        (Point | Box[int], f"hint Point | Box names two classes; {NAME_IT}"),
        (Point | None | Shape, f"hint Point | None | Shape names two classes; {NAME_IT}"),
        (Point | Box | Spot | str, f"hint Point | Box | Spot | str names three classes; {NAME_IT}"),
        (Point | Box | list[int], f"hint Point | Box | list[int] names two classes; {NAME_IT}"),
    ],
)
def test_a_hint_that_names_no_one_class_says_why(hint: object, reason: str) -> None:
    assert hint_check(hint) == NoOneClass(reason)


def test_a_union_of_ten_classes_counts_them_in_digits() -> None:
    classes = [type(f"C{at}", (), {}) for at in range(10)]
    hint = functools.reduce(operator.or_, classes)
    named = " | ".join(f"C{at}" for at in range(10))
    assert hint_check(hint) == NoOneClass(f"hint {named} names 10 classes; {NAME_IT}")


def test_a_protocol_is_told_by_the_mark_typing_sets() -> None:
    # typing.is_protocol on 3.13 and later reads the same mark, which 3.12 sets too
    assert getattr(Drawable, "_is_protocol", None) is True


def test_a_test_that_raises_counts_as_no_hint() -> None:
    assert hint_check(Odd) is None


def test_inside_reads_each_constructor_hint_where_it_was_written() -> None:
    inside = inside_of(Line)

    # Holder is imported only under TYPE_CHECKING, so held has no hint; *rest and **more none
    assert inside.keys == Fields({"start": Builds(Point), "end": Builds(Point), "n": int})
    assert inside.items == Fields({0: Builds(Point), 1: Builds(Point), 3: int})


def test_inside_reads_a_dataclass_s_generated_init() -> None:
    assert inside_of(Spot) == Inside(
        Fields({"at": Builds(Point), "label": str}), Fields({0: Builds(Point), 1: str})
    )


def test_inside_reads_a_class_whose_hint_names_itself_one_level() -> None:
    assert inside_of(Node).keys == Fields({"value": int, "next": Builds(Node)})


def test_inside_skips_a_text_hint_two_modules_read_differently() -> None:
    assert inside_of(Split) == Inside(Fields({}), Fields({}))


def test_inside_of_a_class_python_cannot_read_is_empty() -> None:
    with pytest.raises(ValueError, match="signature"):
        inspect.signature(datetime.date)
    assert inside_of(datetime.date) == Inside(Fields({}), Fields({}))


def test_inside_is_read_once_per_class() -> None:
    assert inside_of(Line) is inside_of(Line)


def test_checked_annotations_reads_with_the_hint_reader() -> None:
    def ship(order: Line, n: int, s: Shape) -> None:
        return None

    checks = checked_annotations(inspect.signature(ship), ship, hint_check)

    assert checks == {
        "order": Builds(Line),
        "n": int,
        "s": NoOneClass(f"hint Shape is an abstract class; {NAME_IT}"),
    }
