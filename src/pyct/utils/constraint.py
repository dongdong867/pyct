from __future__ import annotations

from typing import List, Optional

from pyct.predicate import Predicate


class ConstraintRegistry:
    """Registry for all constraint nodes created during exploration.

    This is a static utility — all methods operate on a module-level list.
    No singleton pattern, no instance state.
    """

    _constraints: List[Constraint] = []

    @classmethod
    def set_constraints(cls, constraints: List[Constraint]) -> None:
        """Replace the constraint list (called after receiving from child process)."""
        cls._constraints = list(constraints)

    @classmethod
    def register(cls, constraint: Constraint) -> int:
        """Register a new constraint and return its ID (index in the list)."""
        constraint_id = len(cls._constraints)
        cls._constraints.append(constraint)
        return constraint_id

    @classmethod
    def get(cls, constraint_id: int) -> Constraint:
        """Get a constraint by its ID."""
        return cls._constraints[constraint_id]

    @classmethod
    def get_all(cls) -> List[Constraint]:
        """Get a copy of all registered constraints."""
        return cls._constraints.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered constraints."""
        cls._constraints.clear()

    @classmethod
    def size(cls) -> int:
        """Get the number of registered constraints."""
        return len(cls._constraints)


class Constraint:
    """A node in the constraint tree.

    Each constraint represents a branch point in execution, defined by a
    predicate (the condition) and a parent (the path that led here).
    Constraints reference each other by ID (index into ConstraintRegistry)
    rather than direct references, because they are pickled across processes.
    """

    def __init__(
        self,
        parent_id: Optional[int],
        predicate: Optional[Predicate],
        depth: int = 0,
    ):
        self.parent_id = parent_id
        self.predicate = predicate
        self.children_ids: List[int] = []
        self.depth = depth
        self.processed = False
        self.id = ConstraintRegistry.register(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Constraint):
            return NotImplemented
        return self.parent_id == other.parent_id and self.predicate == other.predicate

    def __str__(self) -> str:
        predicates = self.get_path_predicates()
        return f"{[str(p) for p in predicates]}  (path_len: {self.depth})"

    def __repr__(self) -> str:
        return (
            f"Constraint(id={self.id}, parent_id={self.parent_id}, "
            f"predicate={self.predicate}, depth={self.depth})"
        )

    @property
    def parent(self) -> Optional[Constraint]:
        """Get the parent constraint, or None for root."""
        if self.parent_id is None:
            return None
        return ConstraintRegistry.get(self.parent_id)

    @property
    def children(self) -> List[Constraint]:
        """Get all child constraints."""
        return [ConstraintRegistry.get(cid) for cid in self.children_ids]

    def add_child(self, predicate: Predicate) -> Constraint:
        """Create and register a child constraint."""
        child = Constraint(
            parent_id=self.id,
            predicate=predicate,
            depth=self.depth + 1,
        )
        self.children_ids.append(child.id)
        return child

    def find_child(self, predicate: Predicate) -> Optional[Constraint]:
        """Find a child with the given predicate, or None."""
        for child_id in self.children_ids:
            child = ConstraintRegistry.get(child_id)
            if child.predicate == predicate:
                return child
        return None

    def get_or_create_child(self, predicate: Predicate) -> Constraint:
        """Get existing child or create a new one."""
        existing = self.find_child(predicate)
        return existing if existing is not None else self.add_child(predicate)

    def get_path_predicates(self) -> List[Predicate]:
        """Collect all predicates from root to this node (marks as processed)."""
        self.processed = True
        predicates: List[Predicate] = []
        current: Optional[Constraint] = self

        while current is not None and current.predicate is not None:
            predicates.append(current.predicate)
            current = current.parent

        return list(reversed(predicates))

    def get_path_constraints(self) -> List[Constraint]:
        """Collect all constraint nodes from root to this node."""
        constraints: List[Constraint] = []
        current: Optional[Constraint] = self

        while current is not None:
            constraints.append(current)
            current = current.parent

        return list(reversed(constraints))

    def is_root(self) -> bool:
        """Check if this is the root constraint."""
        return self.parent_id is None

    def is_leaf(self) -> bool:
        """Check if this has no children."""
        return len(self.children_ids) == 0
