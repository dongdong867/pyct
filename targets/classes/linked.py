"""A class whose hint names itself in quotes inside ``Optional``, as typed code before 3.10
writes it, with no ``from __future__ import annotations``."""

from typing import Optional


class Link:
    def __init__(self, value: int, next: Optional["Link"] = None) -> None:  # noqa: UP037, UP045
        self.value = value
        self.next = next


def head(n: Optional["Link"]):  # noqa: UP037, UP045
    if n is None:
        return "empty"
    if n.next is not None and n.next.value > 5:
        return "big"
    return "small"
