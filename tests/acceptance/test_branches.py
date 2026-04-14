"""Acceptance tests for branching behaviors (behaviors 1, 2, 3)."""


def test_single_if_else_covers_both_branches():
    """
    Given a target with a single if/else branch on a numeric input
    When run_concolic is invoked with an arbitrary initial value
    Then the engine should discover inputs that drive both arms
      And coverage should reach at least 95%
      And at least 2 distinct inputs should be generated
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.single_if_else import classify

    result = run_concolic(target=classify, initial_args={"x": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2
    assert len(result.inputs_generated) >= 2


def test_nested_conditions_covers_all_combinations():
    """
    Given a target with nested if/else on two independent inputs
    When run_concolic is invoked from a single-quadrant seed
    Then the engine should discover all four (x, y) sign combinations
      And coverage should reach at least 95%
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.nested_conditions import categorize

    result = run_concolic(target=categorize, initial_args={"x": 0, "y": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 4


def test_multi_way_elif_reaches_every_arm():
    """
    Given a target with a 5-way if/elif chain (grades A through F)
    When run_concolic starts from a mid-range seed score
    Then the engine should generate inputs hitting every arm
      And coverage should reach at least 95%
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.multi_way_elif import grade

    result = run_concolic(target=grade, initial_args={"score": 50})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 5


def test_function_with_no_branches_still_succeeds():
    """
    Given a pure function with no symbolic branches
    When run_concolic is invoked with any input
    Then exploration should succeed with trivial full coverage
      And at least one path should be recorded
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.no_branches import double

    result = run_concolic(target=double, initial_args={"x": 1})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 1


def test_unreachable_branch_does_not_crash_engine():
    """
    Given a target with a provably unsatisfiable branch (x != x)
    When run_concolic attempts to reach that branch
    Then the solver should fail to satisfy the unreachable arm (UNSAT)
      And the engine should still report success for the reachable arm
      And no unhandled solver exception should propagate
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.branches.unreachable import unreachable

    result = run_concolic(target=unreachable, initial_args={"x": 0})

    assert result.success
    # Reachable arm is covered; the unreachable arm drags the percent below 100
    assert result.coverage_percent > 0
    assert result.paths_explored >= 1
