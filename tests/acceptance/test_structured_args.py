"""Acceptance tests for structured (dict / list / object) arguments.

Primitives nested inside a container or object would be invisible to
the solver without the binding table: wrapping only top-level arguments
leaves the target running concretely, so exploration stops after the seed.

Each test asserts on a *witness*: a specific generated input that could
only come from the solver reasoning about an individual leaf. Coverage
percentages alone would pass for the wrong reasons.
"""


def test_nested_dict_leaves_are_solved_individually():
    """
    Given a target whose branches read primitives two dict levels deep
    When run_concolic starts from a seed that takes none of those branches
    Then the solver should drive the nested port value past both bounds
      And should satisfy the cross-field branch needing workers and port together
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.structured.nested_dict import validate_config

    seed = {"config": {"server": {"port": 100, "workers": 2}}}
    result = run_concolic(target=validate_config, initial_args=seed)

    assert result.success
    ports = [r.args["config"]["server"]["port"] for r in result.inputs_generated]
    assert any(p < 1 for p in ports), f"no input drove port below 1: {ports}"
    assert any(p > 65535 for p in ports), f"no input drove port above 65535: {ports}"
    assert any(
        r.args["config"]["server"]["workers"] > 16 and r.args["config"]["server"]["port"] == 8080
        for r in result.inputs_generated
    ), "no input satisfied the cross-field workers/port branch"


def test_list_elements_get_independent_symbolic_names():
    """
    Given a target that compares two distinct list elements to each other
    When run_concolic starts from a list whose elements differ
    Then each element should be solved independently
      And no solver call should fail on a malformed formula
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.structured.list_items import classify_pair

    result = run_concolic(target=classify_pair, initial_args={"items": [1, 2]})

    assert result.success
    assert all(
        isinstance(r.args["items"], list) and len(r.args["items"]) == 2
        for r in result.inputs_generated
    ), "an iteration received something other than a 2-element list"
    firsts = [r.args["items"][0] for r in result.inputs_generated]
    assert any(v > 100 for v in firsts), f"no input drove items[0] above 100: {firsts}"
    assert any(r.args["items"][1] < -50 for r in result.inputs_generated), (
        "no input drove items[1] below -50"
    )
    assert result.gen_unknown == 0, (
        f"solver reported {result.gen_unknown} UNKNOWN/ERROR results — "
        "undeclared variables produce malformed formulas"
    )


def test_object_attributes_are_solved_individually():
    """
    Given a target branching on attributes of a custom object
    When run_concolic starts from an instance taking none of those branches
    Then the solver should drive the numeric attribute past both bounds
      And should reach the branch gated on the string attribute
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.structured.object_attrs import Rule, classify_rule

    result = run_concolic(target=classify_rule, initial_args={"rule": Rule()})

    assert result.success
    limits = [r.args["rule"].limit for r in result.inputs_generated]
    assert any(v > 100 for v in limits), f"no input drove limit above 100: {limits}"
    assert any(v < 0 for v in limits), f"no input drove limit below 0: {limits}"
    assert any(r.args["rule"].label == "strict" for r in result.inputs_generated), (
        "no input reached the strict-label branch"
    )
