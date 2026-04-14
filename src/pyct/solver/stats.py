from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SolverStats:
    """Tracks solver execution statistics."""

    sat_number: int = 0
    sat_time: float = 0.0
    unsat_number: int = 0
    unsat_time: float = 0.0
    otherwise_number: int = 0
    otherwise_time: float = 0.0

    def record_sat(self, elapsed: float) -> None:
        """Record a SAT result."""
        self.sat_number += 1
        self.sat_time += elapsed

    def record_unsat(self, elapsed: float) -> None:
        """Record an UNSAT result."""
        self.unsat_number += 1
        self.unsat_time += elapsed

    def record_unknown(self, elapsed: float) -> None:
        """Record an UNKNOWN/ERROR result."""
        self.otherwise_number += 1
        self.otherwise_time += elapsed

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "sat_number": self.sat_number,
            "sat_time": self.sat_time,
            "unsat_number": self.unsat_number,
            "unsat_time": self.unsat_time,
            "otherwise_number": self.otherwise_number,
            "otherwise_time": self.otherwise_time,
        }
