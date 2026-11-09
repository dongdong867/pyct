"""The classes and names ``test_classes`` reads a ``"__class__"`` text into."""


class Outer:
    """A class with a class inside it, read as ``Outer.Inner``."""

    class Inner:
        pass


def helper() -> None:
    """A name that is not a class."""
