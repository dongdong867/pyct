"""A NamedTuple whose fields are hinted under postponed annotations, so its signature holds each
hint as a ``ForwardRef``."""

from __future__ import annotations

from typing import NamedTuple


class LaterPoint(NamedTuple):
    x: int
    tags: list[str]
