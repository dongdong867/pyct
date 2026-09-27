"""A sweep fixture: the functions of seeds and defaults with every annotation kept as text."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal


class Mode(enum.Enum):
    FAST = 1
    SLOW = 2


def f(
    a: int,
    b: float,
    c: str,
    d: bool,
    e: list[int],
    g: dict[str, int],
    h: int | None,
    i: str | None,
    j: Sequence[str],
    k: Literal["x", "y"],
    m: None,
    n,
    p: Any,
) -> str:
    if a > 0:
        return "positive"
    return "other"


def with_defaults(
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


def load(data: bytes) -> int:
    return len(data)
