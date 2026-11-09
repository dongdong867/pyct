"""Containers a seed given through run() holds, each of its own type, and a target that reads
a value inside each."""

from collections import namedtuple
from dataclasses import dataclass

Pair = namedtuple("Pair", ["left", "right"])


@dataclass(frozen=True)
class Frozen:
    n: int


def five_reads(point, pair, frozen, ordered, by_id):
    above = 0
    if point[0] > 5:
        above += 1
    if pair.left > 5:
        above += 1
    if frozen.n > 5:
        above += 1
    if ordered["k"] > 5:
        above += 1
    if by_id[1] > 5:
        above += 1
    return above
