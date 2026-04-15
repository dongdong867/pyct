"""Unit tests for PathConstraintTracker."""

from __future__ import annotations

import pytest

from pyct.core.bool import ConcolicBool
from pyct.engine.path import BranchResult, PathConstraintError, PathConstraintTracker
from pyct.predicate import Predicate
from pyct.utils.constraint import ConstraintRegistry


@pytest.fixture(autouse=True)
def _clear_constraint_registry():
    """Keep each path test isolated from the shared Constraint registry."""
    ConstraintRegistry.clear()
    yield
    ConstraintRegistry.clear()


class TestTrackerInitialization:
    def test_tracker_initializes_with_root_constraint(self):
        tracker = PathConstraintTracker()
        assert tracker.root_constraint is not None
        assert tracker.current_constraint is tracker.root_constraint
        # Root predicate is the sentinel None value
        assert tracker.root_constraint.predicate is None


class TestAddBranch:
    def test_add_branch_creates_new_tree_nodes(self):
        tracker = PathConstraintTracker()
        queue: list = []
        condition = ConcolicBool(True, expr=["=", "x_VAR", "5"])

        tracker.add_branch(condition, queue)

        # Tracker advanced from root into the taken child
        assert tracker.current_constraint is not tracker.root_constraint
        # The alternative (negated) path is queued for later exploration
        assert len(queue) == 1
        # Root now has exactly two children: taken and negated
        assert len(tracker.root_constraint.children_ids) == 2

    def test_add_branch_walks_deeper_on_successive_calls(self):
        tracker = PathConstraintTracker()
        queue: list = []
        cond1 = ConcolicBool(True, expr=["=", "x_VAR", "5"])
        cond2 = ConcolicBool(False, expr=[">", "y_VAR", "0"])

        tracker.add_branch(cond1, queue)
        first_depth = tracker.current_constraint.depth

        tracker.add_branch(cond2, queue)
        second_depth = tracker.current_constraint.depth

        assert second_depth == first_depth + 1
        # Two branches → two alternative paths queued
        assert len(queue) == 2

    def test_add_branch_reuses_existing_branch(self):
        tracker = PathConstraintTracker()
        queue: list = []
        cond = ConcolicBool(True, expr=["=", "x_VAR", "5"])

        tracker.add_branch(cond, queue)
        first_current = tracker.current_constraint
        tracker.reset()
        tracker.add_branch(cond, queue)

        # Same physical tree node — not a duplicate
        assert tracker.current_constraint is first_current
        # No new alternative queued because the branch already existed
        assert len(queue) == 1

    def test_add_branch_with_complex_list_expression(self, engine):
        tracker = PathConstraintTracker()
        queue: list = []
        nested_expr = ["and", ["=", "x_VAR", "5"], [">", "y_VAR", "0"]]
        # engine is required so Concolic._resolve_expression preserves the list
        # expression instead of degrading to the concrete value.
        condition = ConcolicBool(True, expr=nested_expr, engine=engine)

        tracker.add_branch(condition, queue)

        # Tracker advanced; branch was successfully constructed
        assert tracker.current_constraint is not tracker.root_constraint
        assert len(queue) == 1
        # The queued alternative has a negated predicate for the same expr
        alternative = queue[0]
        assert alternative.predicate.expr == nested_expr
        assert alternative.predicate.value is False

    def test_negated_and_taken_paths_are_independent_children(self):
        tracker = PathConstraintTracker()
        queue: list = []
        cond = ConcolicBool(True, expr=["=", "x_VAR", "5"])

        tracker.add_branch(cond, queue)

        taken = tracker.current_constraint
        alternative = queue[0]
        assert taken is not alternative
        # Both are direct children of the root
        assert taken.parent is tracker.root_constraint
        assert alternative.parent is tracker.root_constraint
        # Predicates have opposite values
        assert taken.predicate.value is True
        assert alternative.predicate.value is False


class TestReset:
    def test_reset_returns_to_root_while_tree_is_preserved(self):
        tracker = PathConstraintTracker()
        queue: list = []
        cond = ConcolicBool(True, expr=["=", "x_VAR", "5"])

        tracker.add_branch(cond, queue)
        tracker.reset()

        assert tracker.current_constraint is tracker.root_constraint
        # Tree survives the reset
        assert len(tracker.root_constraint.children_ids) == 2

    def test_add_branch_after_reset_navigates_existing_tree(self):
        tracker = PathConstraintTracker()
        queue: list = []
        cond = ConcolicBool(True, expr=["=", "x_VAR", "5"])

        tracker.add_branch(cond, queue)
        original_taken = tracker.current_constraint
        tracker.reset()
        tracker.add_branch(cond, queue)

        # Should land on the same tree node, not a duplicate
        assert tracker.current_constraint is original_taken


class TestRefactorLocks:
    """These tests lock the M2-B.2a refactor decisions into the contract."""

    def test_branch_result_is_frozen(self):
        assert BranchResult.__dataclass_params__.frozen is True

    def test_logger_uses_module_name(self):
        import pyct.engine.path

        assert pyct.engine.path.log.name == "pyct.engine.path"

    def test_tracker_has_no_depth_property(self):
        tracker = PathConstraintTracker()
        # The legacy PathConstraintTracker.depth was deleted during the port
        # because Constraint.depth already tracks this and no caller used it.
        assert not hasattr(tracker, "depth")


class TestInconsistentTreeError:
    def test_add_branch_raises_when_only_one_child_exists(self, engine):
        """Manually corrupt the tree to trigger the inconsistency guard."""
        tracker = PathConstraintTracker()
        queue: list = []
        # Add only the "taken" predicate child, leaving the negated one missing
        expr = ["=", "x_VAR", "5"]
        taken_predicate = Predicate(expr, True)
        tracker.root_constraint.add_child(taken_predicate)

        # engine is required so cond.expr matches the seeded predicate's expr;
        # without it, Concolic drops the list and the tree lookup misses both
        # children, bypassing the inconsistency guard we want to exercise.
        cond = ConcolicBool(True, expr=expr, engine=engine)
        with pytest.raises(PathConstraintError, match="only one branch child"):
            tracker.add_branch(cond, queue)
