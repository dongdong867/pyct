"""The classes the seeds of ``targets.classes.greet`` name with ``"__class__"``."""

from collections import namedtuple
from dataclasses import dataclass

__all__ = ["Account", "Customer", "Guest", "Order", "Pair", "Point", "Profile", "Shop", "Tags"]


class Customer:
    def __init__(self, name, age, vip=False):
        if age < 0:
            raise ValueError("negative age")
        self.name = name
        self.age = age
        self.vip = vip
        self.visits = []


class Order:
    def __init__(self, customer, total):
        self.customer = customer
        self.total = total


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Tags:
    def __init__(self, *names, **extra):
        self.names = names
        self.extra = extra


class Account:
    def __init__(self, owner, plan="free", limit=10, coupon=None, tags=()):
        self.owner = owner
        self.plan = plan
        self.limit = limit
        self.coupon = coupon
        self.tags = tags


class Guest:
    def __init__(self, name: str, age: int, tags: list[str]):
        self.name = name
        self.age = age
        self.tags = tags


@dataclass
class Profile:
    age: int


Pair = namedtuple("Pair", ["left", "right"])


class Shop:
    def __init__(self, owner):
        self.owner = owner

    def serve(self):
        if self.owner.age > 60:
            return "senior"
        return "regular"
