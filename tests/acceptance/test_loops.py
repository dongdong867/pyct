"""Acceptance tests for loop behaviors (behaviors 6, 7)."""


def test_bounded_loop_enters_body():
    """
    Given a target with a bounded loop (for-range based)
    When run_concolic starts from n=0 (body skipped)
    Then the engine should generate n>0 inputs that enter the body
      And coverage should reach at least 95%
      And at least 2 distinct paths should be recorded (skip vs enter)
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.loops.bounded import power_of_two

    result = run_concolic(target=power_of_two, initial_args={"n": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2


def test_data_dependent_loop_terminates():
    """
    Given a target with a data-dependent countdown loop
    When run_concolic starts from n=0
    Then the engine should terminate in a bounded number of iterations
      And explore at least 2 distinct loop-length paths
      And coverage should reach at least 95%
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.loops.data_dependent import countdown

    result = run_concolic(target=countdown, initial_args={"n": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2


def test_loop_with_zero_iterations_still_succeeds():
    """
    Given a bounded loop whose body is skipped when n=0
    When run_concolic is invoked with n=0 (degenerate input)
    Then exploration should still succeed
      And at least the skip-body path should be recorded
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.loops.bounded import power_of_two

    result = run_concolic(target=power_of_two, initial_args={"n": 0})

    assert result.success
    assert result.paths_explored >= 1
