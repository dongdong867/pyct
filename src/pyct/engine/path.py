"""Path constraint tracking — M2-B.2a stub (behavior pending in GREEN commit)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pyct.utils.constraint import Constraint

if TYPE_CHECKING:
    from pyct.core.bool import ConcolicBool

log = logging.getLogger(__name__)


class ConstraintQueue(Protocol):
    """Protocol for constraint queue management."""

    def append(self, constraint: Constraint) -> None:
        """Add a constraint to the queue for later exploration."""
        ...


@dataclass(frozen=True)
class BranchResult:
    """Result of creating a branch in the constraint tree."""

    taken_path: Constraint
    alternative_path: Constraint
    is_new_branch: bool


class PathConstraintError(Exception):
    """Raised when path constraint operations fail."""


class PathConstraintTracker:
    """Tracks the path constraint tree during concolic execution.

    M2-B.2a stub — structural state is real so tests can construct a
    tracker, but behavior methods raise NotImplementedError until the
    GREEN commit wires up the algorithm.
    """

    def __init__(self) -> None:
        self.root_constraint: Constraint = Constraint(None, None)
        self.current_constraint: Constraint = self.root_constraint

    def add_branch(self, condition: ConcolicBool, constraint_queue: ConstraintQueue) -> None:
        raise NotImplementedError(
            "PathConstraintTracker.add_branch not yet implemented — pending M2-B.2a GREEN"
        )

    def reset(self) -> None:
        raise NotImplementedError(
            "PathConstraintTracker.reset not yet implemented — pending M2-B.2a GREEN"
        )
