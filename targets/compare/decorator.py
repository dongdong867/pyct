"""A decorator in a module of its own, for the target in decorated.py."""

import functools
from collections.abc import Callable


def logged(fn: Callable[..., object]) -> Callable[..., object]:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        result = fn(*args, **kwargs)
        return result

    return wrapper
