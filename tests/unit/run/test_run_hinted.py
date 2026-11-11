"""Through run(), an object under a class hint that names no one class: no call, and each input
fails with the place and the reason."""

import pytest

from pyct.results.failure import FailureKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from targets.classes.orders import Item

HINTED = "targets.classes.hinted"
NAME_IT = 'name the class to build with "__class__"'


@pytest.mark.parametrize(
    ("function", "args", "detail"),
    [
        ("draw", {"s": {"side": 1}}, f"building s: hint Shape is an abstract class; {NAME_IT}"),
        ("draw", {"s": [1]}, f"building s: hint Shape is an abstract class; {NAME_IT}"),
        ("render", {"d": {}}, f"building d: hint Drawable is a Protocol; {NAME_IT}"),
        (
            "either",
            {"c": {"name": "ann", "age": 30}},
            f"building c: hint Customer | Guest names two classes; {NAME_IT}",
        ),
    ],
)
def test_an_object_a_hint_cannot_build_fails_its_input_unrun(
    function: str, args: dict[str, object], detail: str
) -> None:
    result = run(
        load_target(f"{HINTED}::{function}"), args, setup=Setup(isolation=Isolation.IN_PROCESS)
    )

    (record,) = result.records
    assert record.failure is not None
    assert record.failure.kind is FailureKind.TARGET_RAISED
    assert record.failure.detail == detail
    assert record.forks == () and record.covered_lines == frozenset()


@pytest.mark.parametrize(
    ("spec", "name"),
    [
        ("targets.classes.linked::head", "n"),
        (f"{HINTED}::chain", "n"),
    ],
)
def test_a_quoted_class_in_a_union_builds_at_the_top_and_inside(spec: str, name: str) -> None:
    seed = {name: {"value": 1, "next": {"value": 2}}}
    fork = [">", ["[]", ["[]", name, "'next'"], "'value'"], 5]

    result = run(load_target(spec), seed, setup=Setup(isolation=Isolation.IN_PROCESS))

    assert all(record.failure is None for record in result.records), result.records
    assert fork in [branch.expression for branch in result.records[0].forks]
    assert any(
        record.args[name]["next"]["value"] > 5  # pyrefly: ignore[bad-index]
        for record in result.records[1:]
        if record.args[name]["next"] is not None  # pyrefly: ignore[bad-index]
    )


def test_instances_a_caller_hands_in_a_list_of_a_class_are_followed() -> None:
    caller = Item("a", 1)

    result = run(
        load_target(f"{HINTED}::total"),
        {"items": [caller]},
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert all(record.failure is None for record in result.records), result.records
    qty = [">", ["getattr", ["[]", "items", 0], "'qty'"], 3]
    assert qty in [branch.expression for branch in result.records[0].forks]
    assert caller.qty == 1


def test_a_library_class_hint_passes_the_json_list() -> None:
    result = run(
        load_target(f"{HINTED}::queued"),
        {"q": [1, 2, 3]},
        setup=Setup(isolation=Isolation.IN_PROCESS),
    )

    assert all(record.failure is None for record in result.records), result.records
    assert any(record.args["q"][0] > 5 for record in result.records[1:])  # pyrefly: ignore
