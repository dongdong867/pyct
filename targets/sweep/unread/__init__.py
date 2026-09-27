"""A sweep fixture: a package that imports cleanly and holds a name that raises when read."""

from .conf import settings


def home(n: int) -> int:
    return n
