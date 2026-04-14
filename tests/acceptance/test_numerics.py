"""Acceptance tests for numeric-constraint behaviors (behavior 8)."""


def test_int_range_covers_all_categories():
    from pyct import run_concolic
    from tests.acceptance.fixtures.numerics.int_range import categorize_value

    result = run_concolic(target=categorize_value, initial_args={"x": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 4


def test_division_by_zero_in_target_does_not_crash_engine():
    """Target that raises ZeroDivisionError should be captured, not
    propagated out of the engine."""
    from pyct import run_concolic
    from tests.acceptance.fixtures.numerics.divide_by import divide

    # n=1 is safe; engine may try n=0 during exploration and should
    # handle the ZeroDivisionError gracefully
    result = run_concolic(target=divide, initial_args={"n": 1})

    assert result is not None
    assert result.paths_explored >= 1
