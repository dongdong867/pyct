"""A class with each kind of method, a nested class, and module-level objects to call."""


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
