"""The classes ``targets.classes.hinted``'s hints name, each hint kept as text, so only this
module resolves the names its constructors' hints use."""

from __future__ import annotations

import abc
import enum
from typing import Generic, Optional, Protocol, TypedDict, TypeVar

T = TypeVar("T")


class Address:
    def __init__(self, city: str, zip_code: int) -> None:
        self.city = city
        self.zip_code = zip_code


class Buyer:
    def __init__(self, name: str, age: int, home: Address | None = None, vip: bool = False):
        if age < 0:
            raise ValueError("negative age")
        self.name = name
        self.age = age
        self.home = home
        self.vip = vip


class Item:
    def __init__(self, sku: str, qty: int) -> None:
        self.sku = sku
        self.qty = qty


class Order:
    def __init__(self, owner: Buyer, items: list[Item], note: str | None = None) -> None:
        self.owner = owner
        self.items = items
        self.note = note


class Box(Generic[T]):  # noqa: UP046 - the spelling typed code of 3.11 and before uses
    def __init__(self, value: T) -> None:
        self.value = value


class Shape(abc.ABC):
    @abc.abstractmethod
    def area(self) -> int: ...


class Square(Shape):
    def __init__(self, side: int) -> None:
        self.side = side

    def area(self) -> int:
        return self.side * self.side


class Drawable(Protocol):
    def draw(self) -> None: ...


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Spec(TypedDict):
    size: int


class Stamp:
    """A class whose constructor signature Python cannot read: ``inspect.signature`` raises
    TypeError on an ``__signature__`` that is no Signature."""

    __signature__ = 0

    def __init__(self, at: int) -> None:
        self.at = at


class Note:
    """A constructor whose ``str`` parameter defaults to None, as untyped code often writes it."""

    def __init__(self, name: str, note: str = None) -> None:  # noqa: RUF013 - what it tests
        self.name = name
        self.note = note


class Node:
    def __init__(self, value: int, next: Optional["Node"] = None) -> None:  # noqa: UP037, UP045
        self.value = value
        self.next = next
