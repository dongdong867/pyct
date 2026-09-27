"""A sweep fixture: functions behind a decorator of this package and behind lru_cache."""

import functools

from ._wrap import logged


@logged
def total(n):
    if n > 3:
        return n
    return 0


@functools.lru_cache
def fetch(key):
    if key == 1:
        return "one"
    return "other"
