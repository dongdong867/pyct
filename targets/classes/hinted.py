"""Functions whose parameters are hinted with classes, each object given as plain JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, Optional

from targets.classes.customers import Customer, Guest, Pair, Point, Profile
from targets.classes.orders import (
    Box,
    Color,
    Drawable,
    Item,
    Node,
    Order,
    Shape,
    Spec,
    Square,
)

if TYPE_CHECKING:
    from targets.classes.orders import Buyer

__all__ = ["Square"]


def greet(c: Customer):
    if c.age > 60:
        return "welcome back"
    return "hello"


def older(p: Profile):
    if p.age > 60:
        return "older"
    return "younger"


def boxed(b: Box[int]):
    if b.value > 5:
        return "big"
    return "small"


def is_a_date(d: date):
    if not isinstance(d, date):
        raise TypeError("not a date")
    return d.year


def placed(p: Point):
    if p.x > 5:
        return "right"
    return "left"


def left_is_big(q: Pair):
    if q.left > 5:
        return "big"
    return "small"


def ship(order: Order):
    if order.owner.age > 60:
        return "care"
    if len(order.items) > 1:
        return "bulk"
    if order.items and order.items[0].qty > 3:
        return "many"
    return "standard"


def deliver(order: Order):
    home = order.owner.home
    if home is not None and home.zip_code > 100:
        return "far"
    return "near"


def ship_any(o):
    if o.owner.age > 60:
        return "care"
    return "standard"


def maybe(c: Customer | None):
    if c is None:
        return "nobody"
    if c.age > 60:
        return "older"
    return "younger"


def maybe_old(c: Optional[Customer]):  # noqa: UP045 - the old spelling is what it tests
    if c is None:
        return "nobody"
    if c.age > 60:
        return "older"
    return "younger"


def paint(color: Color):
    if not isinstance(color, str):
        raise TypeError("not a str")
    if color == "red":
        return "warm"
    return "cool"


def late(c: Buyer):
    if not isinstance(c, dict):
        raise TypeError("not a dict")
    # the solver may drop a key of a dict it tracks, so the key is tested before it is read
    if "age" in c and c["age"] > 60:
        return "older"
    return "younger"


def kept(
    rows: Sequence[Item],
    cfg: Mapping[str, Item],
    spec: Spec,
    pair: tuple[Item, Item],
    ids: dict[int, Item],
):
    # the solver may shorten a list or drop a key it tracks, so each is tested before it is read
    if not (rows and "a" in cfg and pair and 1 in ids and "size" in spec):
        return "short"
    held = (rows[0], cfg["a"], spec, pair[0], ids[1])
    if not all(isinstance(each, dict) for each in held) or not isinstance(pair, list):
        raise TypeError("not kept as JSON")
    if spec["size"] > 3:
        return "big"
    return "small"


def label(x: Customer | str):
    if isinstance(x, str):
        if x == "vip":
            return "vip"
        return "name"
    if x.age > 60:
        return "older"
    return "younger"


def pair_up(c: Customer, n: int, tags: list[int]):
    return n


def draw(s: Shape):
    if s.side > 5:
        return "big"
    return "small"


def either(c: Customer | Guest):
    if c.age > 60:
        return "older"
    return "younger"


def render(d: Drawable):
    return d


def chain(n: "Node"):  # noqa: UP037 - the quoted form is what it tests
    if n.next is not None and n.next.value > 5:
        return "big"
    return "small"
