"""Acceptance tests for branching behaviors (behaviors 1, 2, 3)."""


def test_single_if_else_covers_both_branches():
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.single_if_else import classify

    result = run_concolic(target=classify, initial_args={"x": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2
    assert len(result.inputs_generated) >= 2


def test_nested_conditions_covers_all_combinations():
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.nested_conditions import categorize

    result = run_concolic(target=categorize, initial_args={"x": 0, "y": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 4


def test_multi_way_elif_reaches_every_arm():
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.multi_way_elif import grade

    result = run_concolic(target=grade, initial_args={"score": 50})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 5


def test_function_with_no_branches_still_succeeds():
    """A branch-free target has trivial full coverage — one path."""
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.no_branches import double

    result = run_concolic(target=double, initial_args={"x": 1})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 1


def test_unreachable_branch_does_not_crash_engine():
    """A branch that is provably unsatisfiable should be reported,
    not crash the engine. Coverage will be less than 100% on the
    dead branch, but success is still True."""
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.unreachable import unreachable

    result = run_concolic(target=unreachable, initial_args={"x": 0})

    assert result.success
    # Reachable arm is covered, unreachable arm is not — partial coverage OK
    assert result.coverage_percent > 0
    assert result.paths_explored >= 1
