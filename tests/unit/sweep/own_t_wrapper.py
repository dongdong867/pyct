"""A wrapper and a base whose module binds ``T`` to a type variable of its own."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def logged(fn: Callable[..., object]) -> Callable[..., object]:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        return fn(*args, **kwargs)

    return wrapper


class Base:
    def __init__(self, items: list[T]) -> None:
        self.size = len(items)
