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
