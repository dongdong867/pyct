"""Acceptance tests for point-at-a-class-or-one-of-its-methods: the seed checks under ``self``.

Each test spawns ``python -P -m pyct`` through the harness, on the classes of
``targets/classes/shop.py``, ``targets/classes/sealed.py`` and
``targets/classes/annotated_child.py``, or calls ``run()``. A refusal is a
usage error: exit 2, nothing on stdout, and the reason on stderr.
"""

import inspect
import json
from pathlib import Path

import pytest

from pyct.results.failure import FailureKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from targets.classes import shop
from tests.acceptance.harness import (
    input_lines,
    let_pyct_run_in_process,
    lines_expressions_and_sides,
    run_pyct,
)

SHOP = "targets.classes.shop"
SEALED = "targets.classes.sealed"
# a class whose base, and the text annotations of its methods, are written in another module
ELSEWHERE = "targets.classes.annotated_child"
RESERVED = "pyct reserves keys that start and end with __"
NOT_AN_OBJECT = "self must be a JSON object of {}'s constructor arguments, got {}"


def bind_reason(cls: type, **fields: object) -> str:
    """What plain Python says, in this run, binding ``fields`` to ``cls``'s signature."""
    with pytest.raises(TypeError) as plain:
        inspect.signature(cls).bind(**fields)
    return str(plain.value)


def refused(*argv: str) -> list[str]:
    """The stderr lines of a ``pyct run`` that must be refused as a usage error."""
    result = run_pyct(*argv)
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    return result.stderr.splitlines()


# point-at-a-class-or-one-of-its-methods-refuses-a-self-that-does-not-fit
@pytest.mark.parametrize(
    ("under_self", "expected"),
    [
        (5, NOT_AN_OBJECT.format("Cart", "5")),
        (["ann"], NOT_AN_OBJECT.format("Cart", '["ann"]')),
        ({"colour": "red"}, None),
        ({"owner": 5}, "self['owner'] must be a str, got 5"),
    ],
    ids=["number", "list", "unknown-key", "wrong-type"],
)
def test_refuses_a_self_that_does_not_fit(under_self: object, expected: str | None) -> None:
    seed = json.dumps({"self": under_self, "discount": 1})
    if expected is None:
        expected = f"self (colour) does not fit Cart(owner): {bind_reason(shop.Cart, colour='red')}"

    assert refused(f"{SHOP}::Cart.total", "--args", seed) == [expected]


# point-at-a-class-or-one-of-its-methods-reports-every-contradiction-under-self-at-once
def test_reports_every_contradiction_under_self_at_once() -> None:
    seed = '{"self": {"owner": 5, "colour": "red"}, "discount": "5"}'

    lines = refused(f"{SHOP}::Cart.total", "--args", seed)

    reason = bind_reason(shop.Cart, owner=5, colour="red")
    assert lines == [
        f"self (owner, colour) does not fit Cart(owner): {reason}",
        "self['owner'] must be a str, got 5",
        'discount must be an int, got "5"',
    ]


# point-at-a-class-or-one-of-its-methods-refuses-a-reserved-key-under-self
@pytest.mark.parametrize(
    ("key", "value"), [("__calls__", []), ("__class__", "Box")], ids=["calls", "class"]
)
def test_refuses_a_reserved_key_under_self(key: str, value: object) -> None:
    seed = json.dumps({"self": {"w": 1, key: value}})

    assert refused(f"{SHOP}::Box.size", "--args", seed) == [f"self cannot hold {key!r}: {RESERVED}"]


# point-at-a-class-or-one-of-its-methods-resolves-a-text-annotation-where-the-method-was-written
@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        ('{"self": {"owner": "ann"}, "level": "5"}', 'level must be an int, got "5"'),
        ('{"self": {"owner": 5}, "level": 5}', "self['owner'] must be a str, got 5"),
    ],
    ids=["method", "constructor"],
)
def test_resolves_a_text_annotation_where_the_method_was_written(seed: str, expected: str) -> None:
    assert refused(f"{ELSEWHERE}::Cart.describe", "--args", seed) == [expected]


# point-at-a-class-or-one-of-its-methods-refuses-a-bad-self-in-a-seeds-file
def test_refuses_a_bad_self_in_a_seeds_file(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text(
        '{"self": {"owner": "ann"}, "discount": 1}\n{"self": 5, "discount": 1}\n', encoding="utf-8"
    )

    lines = refused(f"{SHOP}::Cart.total", "--seeds", str(seeds))

    assert lines == [f"{seeds}:2: {NOT_AN_OBJECT.format('Cart', '5')}"]


# point-at-a-class-or-one-of-its-methods-checks-nothing-under-a-self-it-cannot-read: the fit
# and the types are not checked, so a float reaches the constructor and the solver flips its fork
def test_checks_no_fit_or_type_under_a_self_it_cannot_read() -> None:
    result = run_pyct(f"{SEALED}::Sealed.check", "--args", '{"self": {"n": 0.5}}')

    assert result.returncode == 0, result.stderr
    first, *solved = input_lines(result.stdout)
    sides = [side for line in solved for _, _, side in lines_expressions_and_sides(line)]
    assert [side for _, _, side in lines_expressions_and_sides(first)] == [True], result.stdout
    assert False in sides, result.stdout


# point-at-a-class-or-one-of-its-methods-checks-nothing-under-a-self-it-cannot-read: the shape
# and the reserved keys are still checked
@pytest.mark.parametrize(
    ("under_self", "expected"),
    [
        (5, NOT_AN_OBJECT.format("Sealed", "5")),
        ({"n": 1, "__calls__": []}, f"self cannot hold '__calls__': {RESERVED}"),
    ],
    ids=["number", "reserved-key"],
)
def test_still_refuses_a_bad_shape_under_a_self_it_cannot_read(
    under_self: object, expected: str
) -> None:
    seed = json.dumps({"self": under_self})

    assert refused(f"{SEALED}::Sealed.check", "--args", seed) == [expected]


# run() checks no seed: a value under self that is not a JSON object reaches the method as given
def test_run_passes_a_value_under_self_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)
    target = load_target(f"{SHOP}::Cart.total")

    result = run(target, {"self": 5, "discount": 1}, setup=Setup(isolation=Isolation.IN_PROCESS))

    first = result.records[0]
    assert first.args == {"self": 5, "discount": 1}
    assert first.failure is not None
    assert first.failure.kind is FailureKind.TARGET_RAISED
    assert first.failure.detail.startswith("AttributeError: "), first.failure
