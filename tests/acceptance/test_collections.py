"""Acceptance tests for collection-operation behaviors (behavior 9)."""


def test_dict_key_membership_covers_present_and_absent():
    """
    Given a target that checks role membership against a fixed permission dict
    When run_concolic starts from an empty role string
    Then the engine should generate both a known role and a non-existent one
      And coverage should reach at least 95%
      And at least 2 distinct paths should be explored
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.collections.dict_access import get_permission

    result = run_concolic(target=get_permission, initial_args={"role": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2


def test_empty_dict_membership_always_false():
    """
    Given a target whose dict literal is empty (no reachable hit)
    When run_concolic attempts to find a membership-hit
    Then the solver should prove no key satisfies "in empty_dict"
      And the engine should still explore the "not in" path
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.collections.empty_dict import always_absent

    result = run_concolic(target=always_absent, initial_args={"key": "anything"})

    assert result.success
    assert result.paths_explored >= 1
