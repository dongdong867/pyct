"""Acceptance tests for the a-rewrite-reads-an-object-s-fields story's refusals: a rewrite that
calls an object's method, uses the object whole, reads a field of a field or reads an object inside
a list fails its try before anything runs, and no hook of the object's class runs, whichever reply
comes. Each hook of ``targets/rewrites/hooks.py`` writes a file of its own name, so a test that
finds no file saw none run.
"""

from pathlib import Path

import pytest

from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.object_fields import (
    CHARGE,
    CHARGE_AT,
    HINTED_AT,
    HOOKS,
    OBJECTS,
    PAY_HINTED,
    charge_seed,
    form,
    hooks_folder,  # noqa: F401
    tries,
)

# `first(orders, s)`: `if float(orders[0].code) == 1e-30:` on line 23
FIRST = f"{OBJECTS}::first"
# `owned(account)`: `if float(account.owner.code) == 1e-30:` on line 29
OWNED = f"{OBJECTS}::owned"
WHOLE = "a rewrite may read order only as order.<field>"
# a seed whose object holds another of its class
PEERED = {"peer": form("Loud", HOOKS, code="1")}
# every reply llm-rewrite-object-fields-refused-writes-no-file asks with, four to a run
REPLIES = [
    "order.cancel() == 1",
    "order.save() == 1",
    "order == 1",
    "1 == order",
    "order != 1",
    "1 < order",
    "len(order) == 1",
    "bool(order)",
    "not order",
    'str(order) == "x"',
    '"%s" % order == "x"',
    "order in [1]",
    "1 in order",
    "[1][order] == 1",
    "order[0] == 1",
    '"".join(order) == ""',
    "float(order) == 1.0",
    "int(order) == 1",
    "order + 1 == 1",
    "order.total == 1",
    "order.missing == 1",
    "order.peer == 1",
    "order.code == order.peer",
    "order.peer.cancel() == 1",
]


# llm-rewrite-object-fields-refused-a-method-call
def test_a_method_call_fails_its_try_and_never_runs(hooks: Path) -> None:
    provider = FakeRewrites(["order.cancel() == 1"])

    ran = run_rewrites(CHARGE, charge_seed("Loud"), provider)

    assert tries(ran, CHARGE_AT)[0] == "try 1: a rewrite may not call a method of order"
    assert provider.tries[f"{HOOKS}:9:7"] > 1


# llm-rewrite-object-fields-refused-the-object-whole
def test_the_object_used_whole_fails_each_try_and_no_hook_runs(hooks: Path) -> None:
    provider = FakeRewrites(
        ["order == 1", "len(order) == 1", 'str(order) == "x"', 'order["code"] == "1e-30"']
    )

    ran = run_rewrites(CHARGE, charge_seed("Loud"), provider)

    assert tries(ran, CHARGE_AT)[:4] == [f"try {number}: {WHOLE}" for number in range(1, 5)]


# llm-rewrite-object-fields-refused-a-hinted-object-s-key
def test_a_key_of_an_object_a_hint_builds_fails_its_try() -> None:
    ran = run_rewrites(
        PAY_HINTED, {"order": {"code": "0"}}, FakeRewrites(['order["code"] == "1e-30"'])
    )

    assert tries(ran, HINTED_AT)[0] == f"try 1: {WHOLE}"


# llm-rewrite-object-fields-refused-an-object-in-a-list
def test_an_object_in_a_list_fails_its_try() -> None:
    provider = FakeRewrites(['orders[0].code == "1e-30"'])
    seed = {"orders": [form("Order", code="0")], "s": "0"}

    ran = run_rewrites(FIRST, seed, provider)

    at = f"llm: rewrite for {file_of('objects')}:23:7"
    assert tries(ran, at)[0] == "try 1: a rewrite may not read orders, which holds an object"
    assert provider.requests[0].holders == ("orders",)


# llm-rewrite-object-fields-refused-a-field-of-a-field
def test_a_field_of_a_field_fails_its_try() -> None:
    seed = {"account": form("Account", owner=form("Order", code="0"))}

    ran = run_rewrites(OWNED, seed, FakeRewrites(['account.owner.code == "1e-30"']))

    at = f"llm: rewrite for {file_of('objects')}:29:7"
    assert tries(ran, at)[0] == "try 1: a rewrite may not read the attribute code"


# llm-rewrite-object-fields-refused-a-name-with-double-underscores
def test_a_name_with_double_underscores_fails_its_try(hooks: Path) -> None:
    ran = run_rewrites(
        CHARGE, charge_seed("Loud"), FakeRewrites(['order.__dict__["code"] == "1e-30"'])
    )

    assert tries(ran, CHARGE_AT)[0] == "try 1: a rewrite may not read the attribute __dict__"


# llm-rewrite-object-fields-refused-an-attribute-of-a-plain-value
def test_an_attribute_of_a_plain_value_fails_its_try_as_before() -> None:
    # `exponent(s)`: `if float(s) == 1e-30:` on line 2, which the solver gives up on
    ran = run_rewrites("targets.rewrites.text::exponent", {"s": "0"}, FakeRewrites(["s.real > 0"]))

    at = f"llm: rewrite for {file_of('text')}:2:7"
    assert tries(ran, at)[0] == "try 1: a rewrite may not read the attribute real"


# llm-rewrite-object-fields-refused-writes-no-file
@pytest.mark.parametrize("at", range(0, len(REPLIES), 4))
def test_no_reply_runs_a_hook_of_the_object_s_class(hooks: Path, at: int) -> None:
    provider = FakeRewrites(REPLIES[at : at + 4])

    ran = run_rewrites(CHARGE, charge_seed("Loud", **PEERED), provider)

    assert len(tries(ran, CHARGE_AT)) >= 4
