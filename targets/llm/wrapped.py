"""Helpers a target calls behind a decorator that exposes the function it wraps through
``__wrapped__``, for the LLM requests' code of each function a target calls. A condition with
no fork, ``bin(x).count("1")``, leaves a guesses run stuck, so it asks."""

import functools
from collections.abc import Callable
from functools import cache, lru_cache


class Counted:
    """A callable object that keeps the function it wraps in ``__wrapped__``."""

    def __init__(self, fn: Callable[[], str]) -> None:
        functools.update_wrapper(self, fn)
        self.fn = fn

    def __call__(self) -> str:
        return self.fn()


def logged(fn: Callable[[], str]) -> Callable[[], str]:
    @functools.wraps(fn)
    def wrapper() -> str:
        return fn()

    return wrapper


@lru_cache
def _lru_helper() -> str:
    # comment inside the lru_cache helper
    return "lru"


@cache
def _cache_helper() -> str:
    # comment inside the cache helper
    return "cache"


@Counted
def _object_helper() -> str:
    # comment inside the callable object helper
    return "object"


@lru_cache
@logged
def _chained_helper() -> str:
    # comment inside the chained helper
    return "chained"


def wrapped(x: int) -> str:
    texts = [_lru_helper(), _cache_helper(), _object_helper(), _chained_helper()]
    if bin(x).count("1") == 7:
        return "seven"
    return texts[0]


@lru_cache
def again(n: int) -> int:
    if n <= 1:
        return _base()
    return again(n - 1) + again(n - 2)


@lru_cache
def _base() -> int:
    # comment inside the cached base
    return 1
