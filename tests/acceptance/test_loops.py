"""Acceptance tests for loop behaviors (behaviors 6, 7)."""


def test_bounded_loop_enters_body():
    from pyct import run_concolic

    from tests.acceptance.fixtures.loops.bounded import power_of_two

    result = run_concolic(target=power_of_two, initial_args={"n": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    # n=0 skips body, n>0 enters body → at least 2 distinct paths
    assert result.paths_explored >= 2


def test_data_dependent_loop_terminates():
    from pyct import run_concolic

    from tests.acceptance.fixtures.loops.data_dependent import countdown

    result = run_concolic(target=countdown, initial_args={"n": 0})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2
