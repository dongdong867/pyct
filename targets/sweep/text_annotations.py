"""A sweep fixture: annotations kept as text, one naming what only a type checker imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import OrderedDict as Widget


def f(a: int, b: list[str], c: Widget) -> int:
    if a > 1:
        return len(b)
    return 0
