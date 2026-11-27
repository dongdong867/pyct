"""A sweep fixture: functions whose parameters are hinted with the module's own classes, and
those classes' methods."""

import enum
from collections.abc import Callable


class Order:
    def __init__(self, id: int, items: list[str]) -> None:
        self.id = id
        self.items = items

    def total(self, discount: int, strict: bool = False) -> int:
        if strict:
            return max(self.id - discount, 0)
        return self.id - discount

    @staticmethod
    def count(items: list[str]) -> int:
        return len(items)

    @classmethod
    def blank(cls, id: int) -> "Order":
        return cls(id, [])


class Customer:
    def __init__(self, name: str, order: Order) -> None:
        self.name = name
        self.order = order

    def owes(self, amount: int) -> bool:
        return amount > self.order.id


class Keyed:
    def __init__(self, key: Callable[[int], int]) -> None:
        self.key = key

    def run(self, n: int) -> int:
        return self.key(n)


class Hook:
    def __init__(self, keyed: Keyed | None) -> None:
        self.keyed = keyed


class Tag:
    def name(self) -> str:
        return "tag"


class Stamp:
    def __init__(self) -> None:
        self.at = 0


class Basket:
    def __init__(self, order: Order | None = None) -> None:
        self.order = order

    def weigh(self, n: int) -> int:
        return n if self.order is None else n + self.order.id


class Mode(enum.Enum):
    FAST = 1
    SLOW = 2


def ship(order: Order) -> str:
    if order.id > 10:
        return "big"
    return "small"


def maybe(order: Order | None) -> int:
    if order is None:
        return 0
    return order.id


def bill(customer: Customer) -> int:
    return customer.order.id


def apply(keyed: Keyed) -> int:
    return keyed.key(0)


def maybe_apply(keyed: Keyed | None) -> int:
    return 0 if keyed is None else keyed.key(0)


def hooked(hook: Hook) -> bool:
    return hook.keyed is None


def label(tag: Tag, stamp: Stamp) -> str:
    return type(tag).__name__


def pick(mode: Mode) -> int:
    return mode.value


def later(order: Order | None = None) -> int:
    if order is None:
        return 0
    if order.id > 5:
        return 2
    return 1
