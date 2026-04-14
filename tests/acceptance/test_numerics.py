"""Acceptance tests for numeric-constraint behaviors (behavior 8)."""


def test_int_range_covers_all_categories():
    from pyct import run_concolic
    from tests.acceptance.fixtures.numerics.int_range import categorize_value

    result = run_concolic(target=categorize_value, initial_args={"x": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 4
