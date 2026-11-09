"""How long a run may take."""

from dataclasses import dataclass

# the seconds ``pyct run`` gets with no ``--budget``
RUN_SECONDS = 45.0
# the seconds each ``pyct sweep`` entry gets with no ``--budget``
SWEEP_SECONDS = 30.0


@dataclass(frozen=True)
class Budget:
    """The seconds a run may take. ``None`` is no deadline."""

    seconds: float | None = None
