"""A sweep fixture: a subpackage beside the settings, with a module below it."""

from ..conf import settings


def page(n: int) -> int:
    return n
