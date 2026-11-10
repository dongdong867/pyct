"""Acceptance tests for build-an-object-argument-from-its-type-hint, the criteria of
refuse-a-hinted-object-pyct-cannot-build: the seed checks on each object a hint builds.

Each test spawns ``python -P -m pyct`` through the harness on the target functions of
``targets/classes/hinted.py``. A refusal is a usage error: exit 2, nothing on stdout, and the
reasons on stderr.
"""

import inspect
import json
from pathlib import Path

import pytest

from targets.classes import customers, orders
from tests.acceptance.harness import input_lines, run_pyct

HINTED = "targets.classes.hinted"
NAME_IT = 'name the class to build with "__class__"'


def refused(function: str, args: object) -> list[str]:
    """The stderr lines of a ``pyct run`` of ``function`` with ``args``, which must be refused
    as a usage error."""
    result = run_pyct(f"{HINTED}::{function}", "--args", json.dumps(args))
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    return result.stderr.splitlines()


def bind_reason(cls: type, *items: object, **fields: object) -> str:
    """What plain Python says, in this run, binding ``items`` and ``fields`` to ``cls``'s
    signature."""
    with pytest.raises(TypeError) as plain:
        inspect.signature(cls).bind(*items, **fields)
    return str(plain.value)


# build-an-object-argument-from-its-type-hint-builds-a-class-whose-signature-python-cannot-read-unchecked  # noqa: E501
def test_builds_a_class_whose_signature_python_cannot_read_unchecked() -> None:
    with pytest.raises(TypeError) as plain:
        orders.Stamp(at=1, extra=2)  # pyrefly: ignore[unexpected-keyword]

    result = run_pyct(f"{HINTED}::stamped", "--args", json.dumps({"s": {"at": 1, "extra": 2}}))

    assert result.returncode == 0, result.stderr
    failure = input_lines(result.stdout)[0]["failure"]
    assert failure == {"kind": "target_raised", "detail": f"building s: TypeError: {plain.value}"}


# build-an-object-argument-from-its-type-hint-refuses-a-list-that-does-not-fit
def test_refuses_a_list_that_does_not_fit() -> None:
    three = refused("placed", {"p": [1, 2, 3]})
    one = refused("placed", {"p": [1]})

    assert three == [
        f"p (3 items) does not fit Point(x, y): {bind_reason(customers.Point, 1, 2, 3)}"
    ]
    assert one == [f"p (1 item) does not fit Point(x, y): {bind_reason(customers.Point, 1)}"]


# build-an-object-argument-from-its-type-hint-checks-every-level-at-once
EVERY_LEVEL = {
    "order": {
        "owner": {"name": "ann", "age": "30"},
        "items": [{"sku": "a", "qty": "1"}, {"sku": "b"}],
    }
}


def every_level() -> list[str]:
    reason = bind_reason(orders.Item, sku="b")
    return [
        "order['owner']['age'] must be an int, got \"30\"",
        "order['items'][0]['qty'] must be an int, got \"1\"",
        f"order['items'][1] (sku) does not fit Item(sku, qty): {reason}",
    ]


def test_checks_every_level_at_once() -> None:
    assert sorted(refused("ship", EVERY_LEVEL)) == sorted(every_level())


def test_checks_every_level_at_once_in_a_seeds_file(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    fits = {"order": {"owner": {"name": "ann", "age": 30}, "items": []}}
    seeds.write_text(f"{json.dumps(fits)}\n{json.dumps(EVERY_LEVEL)}\n", encoding="utf-8")

    result = run_pyct(f"{HINTED}::ship", "--seeds", str(seeds))

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    expected = [f"{seeds}:2: {line}" for line in every_level()]
    assert sorted(result.stderr.splitlines()) == sorted(expected)


# build-an-object-argument-from-its-type-hint-refuses-a-hint-that-names-no-one-class
def test_refuses_a_hint_that_names_no_one_class() -> None:
    shape = f"hint Shape is an abstract class; {NAME_IT}"

    assert refused("draw", {"s": {"side": 1}}) == [f"s: {shape}"]
    assert refused("draw", {"s": [1]}) == [f"s: {shape}"]
    assert refused("render", {"d": {}}) == [f"d: hint Drawable is a Protocol; {NAME_IT}"]
    assert refused("either", {"c": {"name": "ann", "age": 30}}) == [
        f"c: hint Customer | Guest names two classes; {NAME_IT}"
    ]
    assert refused("draw_all", {"shapes": [{"side": 1}]}) == [f"shapes[0]: {shape}"]


# build-an-object-argument-from-its-type-hint-refuses-a-named-class-that-does-not-fit
def test_refuses_a_named_class_that_does_not_fit() -> None:
    guest = {"__class__": "Guest", "name": "ann", "age": 30, "tags": []}
    customer = {"__class__": "targets.classes.customers::Customer", "name": "ann", "age": 30}

    assert refused("greet", {"c": guest}) == [
        "c['__class__'] must name Customer or a subclass of it, got \"Guest\""
    ]
    assert refused("ship", {"order": {"owner": customer, "items": []}}) == [
        "order['owner']['__class__'] must name Buyer or a subclass of it,"
        ' got "targets.classes.customers::Customer"'
    ]


# a parameter whose default is None accepts null, whatever its hint says (decision
# seed-check-a-none-default-accepts-null)
def test_a_none_default_accepts_null_in_a_hinted_object_and_at_the_top() -> None:
    hinted = run_pyct(f"{HINTED}::noted", "--args", json.dumps({"c": {"name": "a", "note": None}}))
    top = run_pyct(f"{HINTED}::jot", "--args", json.dumps({"name": "a", "note": None}))

    for result in (hinted, top):
        assert result.returncode == 0, result.stderr
        assert input_lines(result.stdout)[0]["failure"] is None, result.stdout
    assert refused("jot", {"name": "a", "note": 5}) == ["note must be a str or null, got 5"]
