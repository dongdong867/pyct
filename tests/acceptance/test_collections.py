"""Acceptance tests for collection-operation behaviors (behavior 9)."""


def test_dict_key_membership_covers_present_and_absent():
    from pyct import run_concolic
    from tests.acceptance.fixtures.collections.dict_access import get_permission

    result = run_concolic(target=get_permission, initial_args={"role": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2
