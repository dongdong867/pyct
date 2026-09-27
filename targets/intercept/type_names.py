from __future__ import annotations


def f(x: int, s: str) -> list[str]:
    seen = []
    if isinstance(x, int) and isinstance(s, str):
        seen.append("instances")
    if type(5) is int:
        seen.append("type")
    return seen
