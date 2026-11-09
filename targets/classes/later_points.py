"""A NamedTuple whose fields are hinted under postponed annotations, so its signature holds each
hint as a ``ForwardRef``."""

from __future__ import annotations

from typing import NamedTuple


class Spot(NamedTuple):
    x: int
    y: int

    def far(self):
        if self.x > 5:
            return "far"
        return "near"
