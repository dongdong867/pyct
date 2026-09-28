"""A tracked int searched in a deque, which Python walks as it walks a tuple or a list."""

from collections import deque
from enum import IntEnum


class Status(IntEnum):
    OK = 0
    BAD = 1


class Ring(deque):
    """A deque that answers `in` itself."""

    def __contains__(self, item: object) -> bool:
        return True


QUEUE = deque([Status.OK, Status.BAD])


def not_queued(x: int) -> str:
    if x not in QUEUE:
        return "new"
    return "queued"


def ring(x: int) -> str:
    if x in Ring([Status.OK]):
        return "found"
    return "missing"
