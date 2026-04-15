"""Path constraint tracking for concolic execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pyct.predicate import Predicate
from pyct.utils.concolic_converter import unwrap_concolic
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

    Maintains a tree of constraints representing all explored and unexplored
    execution paths. Each branch point creates two children: one for the
    condition being true, one for false.
    """

    def __init__(self) -> None:
        self.root_constraint: Constraint = Constraint(None, None)
        self.current_constraint: Constraint = self.root_constraint

    def add_branch(self, condition: ConcolicBool, constraint_queue: ConstraintQueue) -> None:
        """Add a branch point to the constraint tree and advance to the taken path."""
        concrete_value = unwrap_concolic(condition)
        taken_predicate = Predicate(condition.expr, concrete_value)
        negated_predicate = Predicate(condition.expr, not concrete_value)

        branch_result = self._get_or_create_branch(
            taken_predicate, negated_predicate, constraint_queue
        )
        self.current_constraint = branch_result.taken_path

    def _get_or_create_branch(
        self,
        taken_predicate: Predicate,
        negated_predicate: Predicate,
        constraint_queue: ConstraintQueue,
    ) -> BranchResult:
        """Return an existing branch or create a new one at the current node."""
        taken_child = self.current_constraint.find_child(taken_predicate)
        negated_child = self.current_constraint.find_child(negated_predicate)

        if taken_child is None and negated_child is None:
            return self._create_new_branch(taken_predicate, negated_predicate, constraint_queue)
        if taken_child is not None and negated_child is not None:
            return BranchResult(
                taken_path=taken_child,
                alternative_path=negated_child,
                is_new_branch=False,
            )
        raise PathConstraintError(
            "Constraint tree inconsistency: only one branch child exists. "
            f"Taken: {taken_child}, Negated: {negated_child}"
        )

    def _create_new_branch(
        self,
        taken_predicate: Predicate,
        negated_predicate: Predicate,
        constraint_queue: ConstraintQueue,
    ) -> BranchResult:
        """Create child constraints for a new branch point."""
        taken_child = self.current_constraint.add_child(taken_predicate)
        taken_child.processed = True

        negated_child = self.current_constraint.add_child(negated_predicate)
        constraint_queue.append(negated_child)

        log.smtlib2("Now constraint: %s", taken_child)
        log.smtlib2("Add constraint: %s", negated_child)

        return BranchResult(
            taken_path=taken_child,
            alternative_path=negated_child,
            is_new_branch=True,
        )

    def reset(self) -> None:
        """Reset to the root constraint for a new execution path."""
        self.current_constraint = self.root_constraint
