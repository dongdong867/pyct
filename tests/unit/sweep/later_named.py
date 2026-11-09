"""NamedTuples whose fields are hinted under postponed annotations, so each signature holds its
hints as ``ForwardRef``s."""

from __future__ import annotations

from typing import NamedTuple


class Box:
    pass


class Label(NamedTuple):
    text: str
    size: int


class Placed(NamedTuple):
    owner: Box
