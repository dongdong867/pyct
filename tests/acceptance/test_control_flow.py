"""Acceptance tests for control-flow behaviors (behavior 10)."""


def test_early_return_reaches_every_path():
    from pyct import run_concolic

    from tests.acceptance.fixtures.control_flow.early_return import safe_divide

    result = run_concolic(target=safe_divide, initial_args={"a": 1, "b": 1})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 3
