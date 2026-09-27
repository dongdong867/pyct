"""Text annotations that this module and ``own_t_wrapper`` each read with their own ``T``."""

from __future__ import annotations

from typing import TypeVar

from tests.unit.sweep.own_t_wrapper import Base, logged

T = TypeVar("T")


@logged
def first(items: list[T]) -> object:  # noqa: UP047 - the module's own T is the point
    return items[0]


class Child(Base):
    pass
