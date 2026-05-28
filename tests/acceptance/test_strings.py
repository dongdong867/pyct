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


# substr-concrete-start:
#   Given a target with a slice expression `s[5:n]` where 5 is a concrete literal and n is symbolic
#   When the engine emits the substr SMT formula
#   Then the formula does not duplicate the start expression in the substr length term
#     And solve time per formula is ≤ baseline solve time for the same slice depth on the same host
def test_substr_concrete_start_emits_let_bound_formula():
    """
    Given a target with a slice expression `s[5:n]` where 5 is a concrete
      literal and n is symbolic
    When the engine emits the substr SMT formula
    Then the formula does not duplicate the start expression in the substr
      length term — observable via the ``gen_substr_let_bound`` counter on
      the result being non-zero after exploration produced at least one
      substr emission.
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.substr_concrete_start import (
        slice_with_symbolic_end,
    )

    result = run_concolic(
        target=slice_with_symbolic_end,
        initial_args={"s": "hello world", "n": 8},
    )

    assert result.success
    assert result.gen_substr_let_bound > 0


# count-branch-flips:
#   Given a target function with `if s.count(sub) == k:` where sub is a string literal and k is a small concrete int
#     And the seed input value matches the literal sub `k0` times where `k0 != k`
#   When the engine runs pure_concolic exploration
#   Then within 5 iterations the engine produces an input where the literal sub occurs exactly `k` times
#     And the iteration where this occurs reports the branch as flipped vs the seed
def test_count_branch_flips_within_five_iterations():
    """
    Given a target ``if s.count("ab") == 2:`` with a literal sub ``"ab"``
      and concrete k=2, plus a seed ``"xx"`` where the literal occurs 0
      times (k0=0 != k=2)
    When the engine runs pure_concolic exploration
    Then within 5 iterations the engine produces an input where the
      literal sub occurs exactly 2 times — observable as an
      ``InputRecord`` in ``inputs_generated`` whose concrete ``s`` arg
      satisfies ``s.count("ab") == 2``, evidencing the branch was
      flipped vs the seed (which evaluated the equality as False).
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.count_branch import has_two_ab

    result = run_concolic(target=has_two_ab, initial_args={"s": "xx"})

    assert result.success
    assert result.iterations <= 5
    flipped_inputs = [
        record
        for record in result.inputs_generated
        if record.args.get("s", "").count("ab") == 2
    ]
    assert flipped_inputs, (
        "Expected at least one generated input where s.count('ab') == 2; "
        f"got inputs={[r.args for r in result.inputs_generated]}"
    )
    # The flipped iteration is the one that turned the seed's False count==k
    # branch into True — observable via the count-rewrite counter ticking on
    # the SMT emission path that solved for that input.
    assert result.gen_count_rewritten > 0
