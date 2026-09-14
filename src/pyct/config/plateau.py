"""How many inputs a run may spend without covering a new line."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plateau:
    """The inputs a run may spend without gain before it stops. ``None`` is no plateau stop.

    One field, as ``Budget`` is, so the two limits read the same way on a
    signature and on the command line.
    """

    inputs: int | None = None
