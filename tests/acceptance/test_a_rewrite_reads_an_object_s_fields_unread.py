"""Acceptance tests for the a-rewrite-reads-an-object-s-fields story's unread fields: a field the
object does not store itself, or one that holds another object, fails the try with why pyct's
reader read nothing, and none of the class's code runs to find out. Each hook of
``targets/rewrites/hooks.py`` writes a file of its own name, so a test that finds no file saw none
run.
"""

from pathlib import Path

import pytest

from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.object_fields import (
    CHARGE,
    CHARGE_AT,
    HOOKS,
    PAY,
    PAY_AT,
    READS_CODE,
    charge_seed,
    covers,
    form,
    hooks_folder,  # noqa: F401
    order_seed,
    tries,
)

CODE_UNREAD = "try 1: it cannot read order.code:"


# llm-rewrite-object-fields-unread-a-property
# llm-rewrite-object-fields-unread-a-descriptor
# llm-rewrite-object-fields-unread-an-own-getattribute
@pytest.mark.parametrize("cls", ["Prop", "Described", "Gated"])
def test_a_field_the_class_answers_with_code_is_not_read(hooks: Path, cls: str) -> None:
    ran = run_rewrites(CHARGE, charge_seed(cls), FakeRewrites([READS_CODE]))

    assert tries(ran, CHARGE_AT)[0] == f"{CODE_UNREAD} the class reads it with code"


# llm-rewrite-object-fields-unread-a-getattr-answer
# llm-rewrite-object-fields-unread-a-class-attribute
@pytest.mark.parametrize("cls", ["Answering", "ClassCode"])
def test_a_field_the_instance_does_not_store_is_not_read(hooks: Path, cls: str) -> None:
    ran = run_rewrites(CHARGE, charge_seed(cls), FakeRewrites([READS_CODE]))

    assert tries(ran, CHARGE_AT)[0] == f"{CODE_UNREAD} the object holds no such field"


# llm-rewrite-object-fields-unread-a-missing-field
def test_a_missing_field_is_not_read() -> None:
    ran = run_rewrites(PAY, order_seed(), FakeRewrites(["order.cost == 0"]))

    said = "try 1: it cannot read order.cost: the object holds no such field"
    assert tries(ran, PAY_AT)[0] == said


# llm-rewrite-object-fields-unread-a-field-that-holds-an-object
def test_a_field_that_holds_an_object_is_not_read(hooks: Path) -> None:
    seed = charge_seed("Loud", peer=form("Loud", HOOKS, code="1"))

    ran = run_rewrites(CHARGE, seed, FakeRewrites(["order.peer == 1"]))

    said = "try 1: it cannot read order.peer: it holds an object"
    assert tries(ran, CHARGE_AT)[0] == said


# llm-rewrite-object-fields-unread-a-subclass-value
def test_a_field_whose_value_is_a_subclass_of_a_plain_type_is_not_read() -> None:
    # the condition is on s: one on the subclass value is no fork, which no rewrite is asked about
    seed = {"order": form("Coded", code="0"), "s": "0"}

    ran = run_rewrites(CHARGE, seed, FakeRewrites([READS_CODE]))

    assert tries(ran, CHARGE_AT)[0] == f"{CODE_UNREAD} it holds an object"


# llm-rewrite-object-fields-unread-a-field-no-input-sets
def test_a_field_no_input_sets_fails_the_try_and_names_it() -> None:
    ran = run_rewrites(PAY, order_seed("Statused"), FakeRewrites(['order.status == "1e-30"']))

    assert tries(ran, PAY_AT)[0] == "try 1: it reads no value an input sets: order.status"
    assert covers(ran, 6) == []
