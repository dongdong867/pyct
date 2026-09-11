"""How long a run may take."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    """The seconds a run may take. ``None`` is no deadline."""

    seconds: float | None = None
