"""Acceptance tests for build-an-object-the-seed-names-by-its-class: the seed checks on each
object the seed names with ``"__class__"``.

Each test spawns ``python -P -m pyct`` through the harness on the target functions of
``targets/classes/greet.py`` and the classes of ``targets/classes/customers.py``. A refusal is
a usage error: exit 2, nothing on stdout, and the reasons on stderr.
"""

import importlib
import inspect
import json
from pathlib import Path

import pytest

from targets.classes import customers
from tests.acceptance.harness import run_pyct

GREET = "targets.classes.greet"
CUSTOMERS = "targets.classes.customers"
RESERVED = "pyct reserves keys that start and end with __"
BADLY_WRITTEN = "c['__class__'] must be MODULE::CLASS or a class name, got {}"


def refused(target: str, args: object) -> list[str]:
    """The stderr lines of a ``pyct run`` of ``target`` with ``args``, which must be refused as
    a usage error."""
    result = run_pyct(f"{GREET}::{target}", "--args", json.dumps(args))
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    return result.stderr.splitlines()


def customer(cls: object, **fields: object) -> dict[str, object]:
    return {"__class__": cls, "name": "ann", "age": 30, **fields}


def bind_reason(cls: type, **fields: object) -> str:
    """What plain Python says, in this run, binding ``fields`` to ``cls``'s signature."""
    with pytest.raises(TypeError) as plain:
        inspect.signature(cls).bind(**fields)
    return str(plain.value)


def import_error(module: str) -> Exception:
    """What plain Python's import of ``module`` raises, in this run."""
    with pytest.raises(Exception) as plain:
        importlib.import_module(module)
    return plain.value


# build-an-object-the-seed-names-by-its-class-refuses-a-class-that-does-not-load
@pytest.mark.parametrize(
    ("cls", "expected"),
    [
        ("targets.classes.nowhere::Customer", None),
        (f"{CUSTOMERS}::Custmer", f"{CUSTOMERS} has no class Custmer"),
        ("Custmer", f"{GREET} has no class Custmer"),
        (f"{GREET}::greet", f"{GREET}::greet is not a class"),
    ],
    ids=["no-module", "no-class", "bare-name", "not-a-class"],
)
def test_refuses_a_class_that_does_not_load(cls: str, expected: str | None) -> None:
    if expected is None:
        expected = (
            f"cannot import targets.classes.nowhere: {import_error('targets.classes.nowhere')!r}"
        )

    assert refused("greet", {"c": customer(cls)}) == [f"c['__class__']: {expected}"]


# build-an-object-the-seed-names-by-its-class-refuses-a-badly-written-name
@pytest.mark.parametrize("cls", [f"{CUSTOMERS}:Customer", "::Customer"], ids=["colon", "no-module"])
def test_refuses_a_badly_written_name(cls: str) -> None:
    assert refused("greet", {"c": customer(cls)}) == [BADLY_WRITTEN.format(json.dumps(cls))]


# build-an-object-the-seed-names-by-its-class-refuses-keys-the-constructor-does-not-take
def test_refuses_keys_the_constructor_does_not_take() -> None:
    extra = refused("greet", {"c": customer("Customer", colour="red")})
    missing = refused("greet", {"c": {"__class__": "Customer", "name": "ann"}})

    extra_reason = bind_reason(customers.Customer, name="ann", age=30, colour="red")
    missing_reason = bind_reason(customers.Customer, name="ann")
    assert extra == [f"c (name, age, colour) does not fit Customer(name, age, vip): {extra_reason}"]
    assert missing == [f"c (name) does not fit Customer(name, age, vip): {missing_reason}"]


# build-an-object-the-seed-names-by-its-class-refuses-a-reserved-key
def test_refuses_a_reserved_key() -> None:
    lines = refused("greet", {"c": customer("Customer", __calls__=[])})

    assert lines == [f"c cannot hold '__calls__': {RESERVED}"]


# build-an-object-the-seed-names-by-its-class-refuses-a-value-against-a-hint
def test_refuses_a_value_against_a_hint() -> None:
    by_name = refused(
        "welcome", {"g": {"__class__": "Guest", "name": "ann", "age": "30", "tags": ["a", 3]}}
    )
    by_position = refused(
        "welcome", {"g": {"__class__": "Guest", "__args__": ["ann", "30"], "tags": []}}
    )

    assert by_name == ["g['age'] must be an int, got \"30\"", "g['tags'][1] must be a str, got 3"]
    assert by_position == ["g['__args__'][1] must be an int, got \"30\""]


# build-an-object-the-seed-names-by-its-class-reports-every-contradiction-at-once
EVERY_CONTRADICTION = {
    "a": customer("Customer", colour="red"),
    "b": {"__class__": "Guest", "name": "bob", "age": "30", "tags": []},
}


def every_contradiction() -> list[str]:
    reason = bind_reason(customers.Customer, name="ann", age=30, colour="red")
    return [
        f"a (name, age, colour) does not fit Customer(name, age, vip): {reason}",
        "b['age'] must be an int, got \"30\"",
    ]


def test_reports_every_contradiction_at_once() -> None:
    assert refused("pair", EVERY_CONTRADICTION) == every_contradiction()


# build-an-object-the-seed-names-by-its-class-still-refuses-a-class-directly-under-self
def test_still_refuses_a_class_directly_under_self() -> None:
    result = run_pyct(
        f"{CUSTOMERS}::Shop.serve", "--args", '{"self": {"__class__": "Shop", "owner": "ann"}}'
    )

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [f"self cannot hold '__class__': {RESERVED}"]


# build-an-object-the-seed-names-by-its-class-refuses-a-class-or-args-of-the-wrong-kind
def test_refuses_a_class_or_args_of_the_wrong_kind() -> None:
    bad_class = refused("greet", {"c": customer(5)})
    bad_args = refused("greet", {"c": {"__class__": "Customer", "__args__": "ann", "age": 30}})

    assert bad_class == [BADLY_WRITTEN.format(5)]
    assert bad_args == ["c['__args__'] must be a list, got \"ann\""]


# a NamedTuple hinted under postponed annotations, whose signature holds each hint as a
# ForwardRef, is checked against those hints at an object the seed names and under self
LATER = "targets.classes.later_points"


def test_checks_a_named_tuple_hinted_under_postponed_annotations() -> None:
    lines = refused("far", {"p": {"__class__": f"{LATER}::Spot", "__args__": ["a", 2]}})

    assert lines == ["p['__args__'][0] must be an int, got \"a\""]


def test_checks_the_fields_of_a_named_tuple_under_self_hinted_under_postponed_annotations() -> None:
    result = run_pyct(f"{LATER}::Spot.far", "--args", '{"self": {"x": "a", "y": 2}}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["self['x'] must be an int, got \"a\""]


# a seeds file's lines take the same checks, each line after its FILE:N
def test_a_seeds_file_names_every_contradiction_after_its_line(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    fits = {"a": customer("Customer"), "b": customer("Customer")}
    seeds.write_text(f"{json.dumps(fits)}\n{json.dumps(EVERY_CONTRADICTION)}\n", encoding="utf-8")

    result = run_pyct(f"{GREET}::pair", "--seeds", str(seeds))

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [f"{seeds}:2: {line}" for line in every_contradiction()]
