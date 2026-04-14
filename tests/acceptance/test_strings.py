"""Acceptance tests for string-operation behaviors (behaviors 4, 5)."""


def test_string_equality_covers_all_keywords():
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.equality import check_keyword

    result = run_concolic(target=check_keyword, initial_args={"word": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 3


def test_string_contains_covers_match_and_mismatch():
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.contains import has_protocol

    result = run_concolic(target=has_protocol, initial_args={"url": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2


def test_empty_string_branch_reached():
    """Empty string is a boundary case the solver must find."""
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.empty_check import is_empty

    result = run_concolic(target=is_empty, initial_args={"s": "nonempty"})

    assert result.success
    assert result.coverage_percent >= 95.0
    # Engine must find both s=="" and s!="" paths
    assert result.paths_explored >= 2
