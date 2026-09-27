"""A sweep fixture: defaults seed JSON carries, and defaults it cannot."""

import enum
from datetime import datetime


class Mode(enum.Enum):
    FAST = 1
    SLOW = 2


def f(
    x,
    strict=False,
    sep=",",
    ratio=0.5,
    tags=["a"],
    limit: int = None,
    mode=Mode.FAST,
    when=datetime.now,
    *args,
    **kwargs,
) -> str:
    if x > 0:
        return sep.join(tags)
    return "none"


def g(value, /, *, strict: bool) -> str:
    if strict and value:
        return "strict"
    return "loose"
