"""Acceptance tests for string-operation behaviors (behaviors 4, 5)."""


def test_string_equality_covers_all_keywords():
    """
    Given a target that branches on string equality against multiple keywords
    When run_concolic starts from an empty-string seed
    Then the engine should synthesize each matching keyword plus a fallback
      And coverage should reach at least 95%
      And at least 3 distinct paths should be explored
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.equality import check_keyword

    result = run_concolic(target=check_keyword, initial_args={"word": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 3


def test_string_contains_covers_match_and_mismatch():
    """
    Given a target that checks whether a URL contains a protocol prefix
    When run_concolic starts from an empty URL
    Then the engine should generate both a protocol-containing URL and a plain one
      And coverage should reach at least 95%
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.contains import has_protocol

    result = run_concolic(target=has_protocol, initial_args={"url": ""})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2


def test_empty_string_branch_reached():
    """
    Given a target that branches on equality to the empty string
    When run_concolic starts from a non-empty initial value
    Then the engine should discover the empty-string boundary
      And explore both s=="" and s!="" paths
      And coverage should reach at least 95%
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.empty_check import is_empty

    result = run_concolic(target=is_empty, initial_args={"s": "nonempty"})

    assert result.success
    assert result.coverage_percent >= 95.0
    assert result.paths_explored >= 2
