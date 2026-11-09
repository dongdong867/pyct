"""The classes ``test_hints`` reads hints of, each hint kept as text."""

from __future__ import annotations

import abc
import collections
import dataclasses
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from tests.unit.binding.named_classes import Point

if TYPE_CHECKING:
    from tests.unit.binding.named_classes import Holder

T = TypeVar("T")


class Box(Generic[T]):  # noqa: UP046 - the spelling typed code of 3.11 and before uses
    def __init__(self, value: T) -> None:
        self.value = value


class Shape(abc.ABC):
    @abc.abstractmethod
    def area(self) -> int: ...


class Drawable(Protocol):
    def draw(self) -> None: ...


class Abstract(Protocol):
    """A Protocol with an abstract method, named a Protocol."""

    @abc.abstractmethod
    def draw(self) -> None: ...


class Rows(list[int]):
    """A subclass of list, which keeps the JSON value."""


@dataclasses.dataclass
class Spot:
    """A dataclass whose generated ``__init__`` reads its hints in this module."""

    at: Point
    label: str = ""


Pair = collections.namedtuple("Pair", ["left", "right"])


class Line:
    """A constructor whose hints name a class only this module imports, and one only
    ``TYPE_CHECKING`` imports."""

    def __init__(
        self,
        start: Point,
        end: Point | None,
        /,
        held: Holder,
        n: int = 0,
        *rest: Point,
        **more: int,
    ) -> None:
        self.start = start


class Made:
    """A base whose ``__new__`` is written in this module."""

    def __new__(cls, *args: object, **kwargs: object) -> Made:
        return super().__new__(cls)


class Node:
    """A class whose hint names itself."""

    def __init__(self, value: int, next: Node | None = None) -> None:
        self.value = value
        self.next = next
