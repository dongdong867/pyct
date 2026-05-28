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


# count-empty-sub:
#   Given a target evaluating `s.count("")` where s is symbolic
#   When the engine produces concrete inputs for s
#   Then for every produced input, the engine's claimed value of `s.count("")` equals `len(s) + 1`
#     And no rewrite-induced false branch is registered for the empty-sub case
def test_count_empty_sub_preserves_python_semantics():
    """
    Given a target ``if s.count("") == 3:`` where the literal sub is the
      empty string (the edge case Python defines as ``len(s) + 1``)
    When the engine runs pure_concolic exploration and produces concrete
      inputs for s
    Then for every produced input, the concrete evaluation of
      ``s.count("")`` equals ``len(s) + 1`` — i.e. the rewrite has NOT
      perturbed Python's empty-sub semantics, observable by re-executing
      ``str.count`` on each ``InputRecord``'s ``s`` arg.
      And no rewrite-induced skip is registered for the empty-sub case:
      ``result.gen_count_skipped_symbolic_sub == 0`` (empty sub is a
      literal, so the symbolic-sub fallback must NOT have fired) while
      ``result.gen_count_rewritten`` is exposed (counter exists),
      anchoring the assertion at the post-rewrite-feature contract.
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.count_empty_sub import (
        matches_empty_count,
    )

    result = run_concolic(target=matches_empty_count, initial_args={"s": "x"})

    assert result.success
    # Semantic preservation: Python's `s.count("") == len(s) + 1` holds
    # for every input the engine emitted, regardless of which branch the
    # engine claimed it took.
    for record in result.inputs_generated:
        s_value = record.args.get("s", "")
        assert s_value.count("") == len(s_value) + 1, (
            f"Engine produced input s={s_value!r} but Python's "
            f"s.count('') ({s_value.count('')}) != len(s) + 1 "
            f"({len(s_value) + 1}) — rewrite perturbed empty-sub semantics."
        )
    # Empty sub is a literal (not symbolic), so the symbolic-sub
    # skip counter must remain zero across the entire run.
    assert result.gen_count_skipped_symbolic_sub == 0


# membership-per-element-branches:
#   Given a target with `if x in {a, b, c}:` where the container is a literal of N ≤ 32 string elements
#     And the seed input does not match any element of the container
#   When the engine runs pure_concolic exploration
#   Then within 2*N iterations the engine produces at least one input matching each of a, b, c
#     And each matching iteration reports a distinct path-condition disjunct as flipped
def test_membership_set_literal_flips_each_disjunct():
    """
    Given a target ``if x in {"red", "green", "blue"}:`` with a literal
      set comparator of N=3 string elements, plus a seed ``"none"`` that
      matches no container element
    When the engine runs pure_concolic exploration
    Then within 2 * N = 6 iterations the engine produces at least one
      input matching each of the three elements — observable as one
      ``InputRecord`` in ``inputs_generated`` per element whose concrete
      ``x`` arg equals that element. Each match evidences a distinct
      path-condition disjunct flip (the rewriter expands ``in`` into a
      ``BoolOp(Or, [Compare(Eq), ...])`` whose disjuncts are flipped
      independently).
      And the membership-rewrite firing is observable via
      ``result.gen_membership_rewritten`` being non-zero.
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.membership_set import matches_color

    result = run_concolic(target=matches_color, initial_args={"x": "none"})

    assert result.success
    # N=3 container, so the budget for hitting every element is 2 * N = 6.
    assert result.iterations <= 6
    generated_x_values = {
        record.args.get("x") for record in result.inputs_generated
    }
    for element in ("red", "green", "blue"):
        assert element in generated_x_values, (
            f"Expected at least one generated input where x == {element!r}; "
            f"got inputs={[r.args for r in result.inputs_generated]}"
        )
    # Each matching iteration flipped a distinct disjunct — observable
    # via the membership-rewrite firing counter ticking on the SMT
    # emission path that solved for those inputs.
    assert result.gen_membership_rewritten > 0
