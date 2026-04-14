"""Acceptance tests for control-flow behaviors (behavior 10)."""


def test_early_return_reaches_every_path():
    from pyct import run_concolic
    from tests.acceptance.fixtures.control_flow.early_return import safe_divide

    result = run_concolic(target=safe_divide, initial_args={"a": 1, "b": 1})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 3


def test_target_raising_exception_does_not_crash_engine():
    """Targets that raise runtime exceptions should not propagate out
    of the engine — exploration continues, failure is recorded."""
    from pyct import run_concolic
    from tests.acceptance.fixtures.control_flow.raises_exception import guarded

    result = run_concolic(target=guarded, initial_args={"n": 0})

    assert result is not None
    assert result.paths_explored >= 1
