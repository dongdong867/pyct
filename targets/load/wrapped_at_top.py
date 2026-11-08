"""Module-level callables a decorator or functools wraps, each read from the module's own names."""

import functools


def plain(x):
    if x > 0:
        return "positive"
    return "other"


@functools.lru_cache
def cached(x):
    return plain(x)


@functools.cache
def cached_forever(x):
    return plain(x)


class Logged:
    def __init__(self, function):
        self.function = function
        functools.update_wrapper(self, function)

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    def __get__(self, instance, owner=None):
        return self if instance is None else functools.partial(self, instance)


@Logged
def logged(x):
    return plain(x)


partly = functools.partial(plain)
