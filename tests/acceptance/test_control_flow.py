"""Acceptance tests for control-flow behaviors (behavior 10)."""


def test_early_return_reaches_every_path():
    """
    Given a target with guard-clause early returns (safe_divide)
    When run_concolic starts from a valid input pair
    Then the engine should generate inputs hitting every early return
      And coverage should reach at least 95%
      And at least 3 distinct return paths should be recorded
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.control_flow.early_return import safe_divide

    result = run_concolic(target=safe_divide, initial_args={"a": 1, "b": 1})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 3


def test_target_raising_exception_does_not_crash_engine():
    """
    Given a target that raises ValueError on some input (n < 0)
    When run_concolic may try a negative input during exploration
    Then the engine should capture the exception internally
      And continue exploration for at least the happy path
      And return a result without propagating the exception to the caller
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.control_flow.raises_exception import guarded

    result = run_concolic(target=guarded, initial_args={"n": 0})

    assert result is not None
    assert result.paths_explored >= 1
