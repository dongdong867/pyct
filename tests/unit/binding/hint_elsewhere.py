"""A class whose constructor's text hint this module reads one way, and its base's module
another."""

from __future__ import annotations

from tests.unit.binding.hint_classes import Box as Point
from tests.unit.binding.hint_classes import Made


class Split(Made):
    def __init__(self, at: Point) -> None:
        self.at = at
