"""Shared fixtures for all pyct tests.

Provides:
- Automatic ConstraintRegistry isolation (autouse).
- MockEngine with path/solver/constraints_to_solve for concolic type tests.
"""

from __future__ import annotations

from collections import deque
from typing import Any, List, Optional, Tuple

import pytest

from pyct.utils.constraint import ConstraintRegistry


# ---------------------------------------------------------------------------
# ConstraintRegistry isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_constraint_registry():
    """Ensure ConstraintRegistry is empty before and after every test."""
    ConstraintRegistry.clear()
    yield
    ConstraintRegistry.clear()


# ---------------------------------------------------------------------------
# MockEngine and helpers
# ---------------------------------------------------------------------------


class MockSolver:
    """Minimal solver stub that records validate_expression calls."""

    def __init__(self) -> None:
        self.validate_calls: List[Tuple[Any, Any]] = []

    def validate_expression(self, expr: Any, value: Any) -> Optional["MockEngine"]:
        """Record the call and return None (no validation)."""
        self.validate_calls.append((expr, value))
        return None


class MockPath:
    """Minimal path-constraint tracker that records add_branch calls."""

    def __init__(self) -> None:
        self.branches: List[Tuple[Any, Any]] = []

    def add_branch(self, condition: Any, queue: Any) -> None:
        """Record the branch decision."""
        self.branches.append((condition, queue))


class MockEngine:
    """Lightweight stand-in for ExplorationEngine.

    Provides the attributes that concolic types access:
    - ``path``  — records branch registrations
    - ``solver`` — records validate_expression calls
    - ``constraints_to_solve`` — empty deque for branch registration
    """

    def __init__(self) -> None:
        self.path = MockPath()
        self.solver = MockSolver()
        self.constraints_to_solve: deque = deque()


@pytest.fixture
def engine() -> MockEngine:
    """Fresh MockEngine for one test."""
    return MockEngine()
