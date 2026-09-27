"""A sweep fixture: a package that imports cleanly and holds a name that raises when read."""

from .conf import settings

# views is a module below, which this package does not import; settings raises when read
__all__ = ["views", "settings", "home"]


def home(n: int) -> int:
    return n
