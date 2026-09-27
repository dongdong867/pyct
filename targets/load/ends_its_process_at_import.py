"""A module that ends its process with ``os._exit(3)`` while it is imported."""

import os

os._exit(3)


def f(x: int) -> int:
    return x
