"""The classes and names ``test_classes`` reads a ``"__class__"`` text into."""


class Outer:
    """A class with a class inside it, read as ``Outer.Inner``."""

    class Inner:
        pass


def helper() -> None:
    """A name that is not a class."""


class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class Pinned:
    """A constructor whose first parameter goes by position only."""

    def __init__(self, a: int, /, b: int = 0) -> None:
        self.a = a
        self.b = b


class Holder:
    def __init__(self, inner: object, other: object = None) -> None:
        self.inner = inner
        self.other = other
