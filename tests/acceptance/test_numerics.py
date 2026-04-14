"""Acceptance tests for numeric-constraint behaviors (behavior 8)."""


def test_int_range_covers_all_categories():
    """
    Given a target that classifies an integer into 4 ranges
    When run_concolic starts from x=0
    Then the engine should generate inputs hitting every range category
      And coverage should reach at least 95%
      And at least 4 distinct paths should be explored
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.numerics.int_range import categorize_value

    result = run_concolic(target=categorize_value, initial_args={"x": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 4


def test_division_by_zero_in_target_does_not_crash_engine():
    """
    Given a target that divides by its input (ZeroDivisionError on n=0)
    When run_concolic starts from a safe n=1
    Then the engine may try n=0 during exploration
      And should capture the exception internally rather than propagate it
      And return a result (possibly with error populated) without crashing
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.numerics.divide_by import divide

    result = run_concolic(target=divide, initial_args={"n": 1})

    # Engine must have explored at least one path — confirms the engine
    # didn't crash out on the ZeroDivisionError that n=0 would trigger.
    assert result.paths_explored >= 1
    # Either the run succeeded (engine avoided n=0) or the exception was
    # captured as an error. Either way, no exception propagates here.
    assert result.success or result.error is not None
