"""A sweep fixture: one parameter for each kind of annotation a seed is chosen from."""

from collections.abc import Sequence
from typing import Any, Literal


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
