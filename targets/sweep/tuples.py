"""A sweep fixture: named tuples, functional and class-syntax, and a dataclass."""

import collections
from dataclasses import dataclass
from typing import NamedTuple

Pair = collections.namedtuple("Pair", "a b")


class Point(NamedTuple):
    x: int
    y: int


class Span(NamedTuple):
    start: int
    end: int

    def length(self) -> int:
        return self.end - self.start


@dataclass
class Box:
    width: int
    label: str = "box"
