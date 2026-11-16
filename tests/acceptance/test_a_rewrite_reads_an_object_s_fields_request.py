"""Acceptance tests for the a-rewrite-reads-an-object-s-fields story's request: it shows an object
the input builds as its class and the arguments it is built from, a `run()` caller's instance as
its class alone, and a parameter that holds an object inside a list as one a condition may not
read; its form says how a condition reads an object. Each hook of ``targets/rewrites/hooks.py``
writes a file of its own name, so a test that finds no file saw none run.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

from pyct.llm.rewrites import request_text
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.object_fields import (
    CHARGE,
    HOOKS,
    OBJECTS,
    PAY,
    PAY_HINTED,
    READS_CODE,
    form,
    hooks_folder,  # noqa: F401
    instance,
    order_seed,
)

BUILT = '<Order object, built from {"code": "0"}>'


def first_request(
    spec: str, seed: Mapping[str, object] | Callable[[], Mapping[str, object]]
) -> str:
    """The text of the first request the run on ``spec`` from ``seed`` asks with."""
    provider = FakeRewrites([READS_CODE])
    run_rewrites(spec, seed, provider)
    return request_text(provider.requests[0])


# llm-rewrite-object-fields-request-shows-a-seed-named-object
def test_an_object_a_seed_names_is_shown_with_what_it_is_built_from() -> None:
    text = first_request(PAY, order_seed())

    assert f"\norder = {BUILT}\n" in text
    assert "a field of a parameter that is an object, written order.code, one level deep" in text
    assert "never the object whole and never its methods" in text
    assert "a method's self among them" in text


# llm-rewrite-object-fields-request-shows-an-object-a-hint-builds
def test_an_object_a_hint_builds_is_shown_with_what_it_is_built_from() -> None:
    text = first_request(PAY_HINTED, {"order": {"code": "0"}})

    assert f"\norder = {BUILT}\n" in text
    assert 'order = {"code": "0"}' not in text


# llm-rewrite-object-fields-request-shows-self
def test_a_method_s_self_is_shown_as_its_class_with_what_it_is_built_from() -> None:
    text = first_request(f"{OBJECTS}::Till.pay", {"self": {"code": "0"}})

    assert '\nself = <Till object, built from {"code": "0"}>\n' in text


# llm-rewrite-object-fields-request-shows-an-instance-without-running-it
def test_an_instance_a_run_caller_hands_in_is_its_class_alone(hooks: Path) -> None:
    def seed() -> dict[str, object]:
        return {"order": instance(HOOKS, "Shown", "0"), "s": "0"}

    text = first_request(CHARGE, seed)

    assert "\norder = <Shown object>\n" in text


# llm-rewrite-object-fields-request-lists-what-may-not-be-read
def test_a_parameter_holding_an_object_in_a_list_is_listed_as_unreadable() -> None:
    text = first_request(f"{OBJECTS}::first", {"orders": [form("Order", code="0")], "s": "0"})

    assert "\norders = <holds an object>\n" in text
    assert "may not read, since each holds an object inside a list, tuple or dict: orders" in text
