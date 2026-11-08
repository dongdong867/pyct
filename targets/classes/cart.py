"""A class with each kind of method, a nested class, and module-level objects to call."""

import types


class Cart:
    count = 0

    def __init__(self, owner):
        self.owner = owner

    def total(self, discount):
        self.last = discount
        if self.owner == "admin":
            return 0
        if discount > 10:
            return discount - 10
        return discount

    @classmethod
    def from_text(cls, text):
        if text == "admin":
            return cls(text)
        return cls("guest")

    @staticmethod
    def rate(x):
        if x > 5:
            return "high"
        return "low"

    @property
    def size(self):
        return 0


class Outer:
    class Inner:
        def check(self, x):
            if x > 0:
                return "positive"
            return "other"


class Registry:
    def lookup(self, key):
        if key == "b":
            return 2
        return 1


registry = Registry()


class Handler:
    def __call__(self, x):
        if x > 3:
            return "many"
        return "few"


handler = Handler()


class Tags(dict):
    pass


class to_the_class:
    def __init__(self, function):
        self.function = function

    def __get__(self, instance, owner=None):
        return types.MethodType(self.function, type(instance) if owner is None else owner)


class Catalog:
    @to_the_class
    def opened(cls, x):
        if x > 0:
            return cls
        return None


class Store:
    reads = 0

    @property
    def till(self):
        Store.reads += 1
        return handler


store = Store()

prices = {"a": 1}


class Proxy:
    def __getattribute__(self, name):
        return object.__getattribute__(self, name)

    def pick(self, x):
        if x > 2:
            return "big"
        return "small"


proxy = Proxy()
