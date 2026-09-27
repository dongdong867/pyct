"""A sweep fixture: a decorator that keeps the function it wraps."""

import functools


def logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper
