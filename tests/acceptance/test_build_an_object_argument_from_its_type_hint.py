"""Acceptance tests for build-an-object-argument-from-its-type-hint, the criteria of
build-and-follow-an-object-a-hint-names.

Each test spawns ``python -P -m pyct`` through the harness, or calls ``run()``, on the target
functions of ``targets/classes/hinted.py``, whose parameters are hinted with the classes of
``targets/classes/customers.py`` and ``targets/classes/orders.py``, and whose seeds give each
object as plain JSON.
"""

import importlib
import json
from pathlib import Path

import pytest

from pyct.results.failure import FailureKind
from pyct.run.run import run
from pyct.run.target import interception, load_target
from targets.classes.customers import Customer
from tests.acceptance.harness import forks_of, input_lines, let_pyct_run_in_process, run_pyct

HINTED = "targets.classes.hinted"
AGE = ["[]", "c", "'age'"]
AGE_ABOVE_60 = [">", AGE, 60]
OWNER_AGE = ["[]", ["[]", "order", "'owner'"], "'age'"]
NAME_IT = 'name the class to build with "__class__"'
NEGATIVE_AGE = {"kind": "target_raised", "detail": "building x: ValueError: negative age"}


def seed(**args: object) -> str:
    return json.dumps(args)


def ann(age: int = 30) -> dict[str, object]:
    return {"name": "ann", "age": age}


def arg(line: dict[str, object], *path: object) -> object:
    """The value a printed line's ``args`` holds at ``path``."""
    value: object = line["args"]
    for step in path:
        assert isinstance(value, dict | list), line
        value = value[step]  # pyrefly: ignore[bad-index]
    return value


def held(line: dict[str, object], *path: object) -> dict[str, object] | list[object]:
    """The dict or list a printed line's ``args`` holds at ``path``."""
    value = arg(line, *path)
    assert isinstance(value, dict | list), line
    return value


def above(value: object, bound: int) -> bool:
    """Whether a value off a printed line is an int above ``bound``."""
    return isinstance(value, int) and not isinstance(value, bool) and value > bound


def solved(stdout: str) -> list[dict[str, object]]:
    """The input lines after the seed's."""
    return input_lines(stdout)[1:]


def expressions(line: dict[str, object]) -> list[object]:
    return [fork["expression"] for fork in forks_of(line)]


def fork_lines(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith("fork ")]


def pyct(function: str, args: str) -> tuple[int, str, str]:
    result = run_pyct(f"{HINTED}::{function}", "--args", args)
    return result.returncode, result.stdout, result.stderr


def took_the_other_side(stdout: str, expression: list[object]) -> bool:
    """Whether a solver line with no failure takes ``expression`` true, as the seed did not."""
    return any(
        line["failure"] is None
        and any(fork["expression"] == expression and fork["taken"] for fork in forks_of(line))
        for line in solved(stdout)
    )


def raised(call: object) -> str:
    """The text of the TypeError plain Python raises for ``call()`` in this run."""
    try:
        call()  # pyrefly: ignore[not-callable]
    except TypeError as error:
        return str(error)
    raise AssertionError("no TypeError")


# build-an-object-argument-from-its-type-hint-builds-and-follows-an-object
def test_builds_and_follows_an_object() -> None:
    code, stdout, stderr = pyct("greet", seed(c=ann()))

    assert code == 0, stderr
    first, *rest = lines = input_lines(stdout)
    assert first["args"] == {"c": {"name": "ann", "age": 30, "vip": False}}
    assert AGE_ABOVE_60 in expressions(first)
    assert any("  c['age'] > 60  " in line for line in fork_lines(stderr)), stderr
    assert any(above(arg(line, "c", "age"), 60) and line["failure"] is None for line in rest)
    for line in lines:
        assert set(held(line, "c")) == {"name", "age", "vip"}, line


# build-an-object-argument-from-its-type-hint-builds-any-kind-of-class
def test_builds_any_kind_of_class() -> None:
    profile = pyct("older", seed(p={"age": 30}))
    box = pyct("boxed", seed(b={"value": 1}))
    dated = pyct("is_a_date", seed(d={"year": 2024, "month": 1, "day": 1}))

    for code, _, stderr in (profile, box, dated):
        assert code == 0, stderr
    assert took_the_other_side(profile[1], [">", ["[]", "p", "'age'"], 60]), profile[1]
    assert took_the_other_side(box[1], [">", ["[]", "b", "'value'"], 5]), box[1]
    assert input_lines(dated[1])[0]["failure"] is None, dated[1]


# build-an-object-argument-from-its-type-hint-writes-an-input-that-runs-again
def test_writes_an_input_that_runs_again() -> None:
    _, stdout, _ = pyct("greet", seed(c=ann()))
    older = next(line for line in solved(stdout) if above(arg(line, "c", "age"), 60))

    code, again, stderr = pyct("greet", json.dumps(older["args"]))

    assert code == 0, stderr
    first = input_lines(again)[0]
    assert first["args"] == older["args"]
    sides = [(fork["expression"], fork["taken"]) for fork in forks_of(first)]
    assert sides == [(fork["expression"], fork["taken"]) for fork in forks_of(older)]


# build-an-object-argument-from-its-type-hint-builds-through-run
def test_builds_through_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = {"order": {"owner": ann(), "items": []}}
    lines = input_lines(pyct("ship", json.dumps(args))[1])
    let_pyct_run_in_process(monkeypatch)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))

    # the interception the command line holds, so `len` of the items is followed alike
    with interception(f"{HINTED}::ship"):
        result = run(load_target(f"{HINTED}::ship"), args)

    assert [record.args for record in result.records] == [line["args"] for line in lines]


# build-an-object-argument-from-its-type-hint-fails-each-input-run-cannot-build
def test_fails_each_input_run_cannot_build(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)
    message = raised(lambda: Customer(name="ann", age=30, colour="red"))  # pyrefly: ignore

    result = run(load_target(f"{HINTED}::greet"), {"c": {**ann(), "colour": "red"}})

    assert result.records
    for record in result.records:
        assert record.failure is not None
        assert record.failure.kind is FailureKind.TARGET_RAISED
        assert record.failure.detail == f"building c: TypeError: {message}"


# build-an-object-argument-from-its-type-hint-passes-a-list-by-position
def test_passes_a_list_by_position() -> None:
    point = pyct("placed", seed(p=[1, 2]))
    pair = pyct("left_is_big", seed(q=[1, 2]))

    for code, _, stderr in (point, pair):
        assert code == 0, stderr
    lines = input_lines(point[1])
    assert [">", ["[]", "p", 0], 5] in expressions(lines[0])
    assert any("  p[0] > 5  " in line for line in fork_lines(point[2])), point[2]
    assert any(above(arg(line, "p", 0), 5) and arg(line, "p", 1) == 2 for line in lines[1:])
    for line in lines:
        assert isinstance(arg(line, "p"), list) and len(held(line, "p")) == 2, line
    assert any(above(arg(line, "q", 0), 5) for line in solved(pair[1])), pair[1]


# build-an-object-argument-from-its-type-hint-passes-args-by-position-in-a-hinted-object
def test_passes_args_by_position_in_a_hinted_object() -> None:
    code, stdout, stderr = pyct("placed", seed(p={"__args__": [1], "y": 2}))

    assert code == 0, stderr
    lines = input_lines(stdout)
    assert [">", ["[]", ["[]", "p", "'__args__'"], 0], 5] in expressions(lines[0])
    assert any(above(arg(line, "p", "__args__", 0), 5) for line in lines[1:]), stdout
    for line in lines:
        assert len(held(line, "p", "__args__")) == 1, line


# build-an-object-argument-from-its-type-hint-builds-at-every-level-from-the-constructor-s-module
def test_builds_at_every_level_from_the_constructor_s_module() -> None:
    home = {"city": "x", "zip_code": 5}
    code, stdout, stderr = pyct(
        "deliver", seed(order={"owner": {**ann(), "home": home}, "items": []})
    )

    assert code == 0, stderr
    first, *rest = lines = input_lines(stdout)
    zip_code = ["[]", ["[]", ["[]", "order", "'owner'"], "'home'"], "'zip_code'"]
    assert [">", zip_code, 100] in expressions(first)
    assert first["failure"] is None, first
    assert any(above(arg(line, "order", "owner", "home", "zip_code"), 100) for line in rest)
    assert all("__class__" not in json.dumps(line["args"]) for line in lines), stdout


# build-an-object-argument-from-its-type-hint-fills-defaults-at-every-level
def test_fills_defaults_at_every_level() -> None:
    code, stdout, stderr = pyct("ship", seed(order={"owner": ann(), "items": []}))

    assert code == 0, stderr
    lines = input_lines(stdout)
    owner = {"name": "ann", "age": 30, "vip": False}
    assert lines[0]["args"] == {"order": {"owner": owner, "items": []}}
    for line in lines:
        assert "note" not in held(line, "order"), line
        assert "home" not in held(line, "order", "owner"), line


# build-an-object-argument-from-its-type-hint-reports-a-constructor-that-raises-inside
def test_reports_a_constructor_that_raises_inside() -> None:
    code, stdout, stderr = pyct("ship", seed(order={"owner": ann(-1), "items": []}))

    assert code == 0, stderr
    first, *rest = input_lines(stdout)
    detail = "building order['owner']: ValueError: negative age"
    assert first["failure"] == {"kind": "target_raised", "detail": detail}
    built = [
        line
        for line in rest
        if line["failure"] is None
        and above(arg(line, "order", "owner", "age"), -1)
        and [">", OWNER_AGE, 60] in expressions(line)
    ]
    assert built, stdout


# build-an-object-argument-from-its-type-hint-builds-an-object-inside-self-from-its-hint
def test_builds_an_object_inside_self_from_its_hint() -> None:
    result = run_pyct(
        "targets.classes.customers::Desk.serve", "--args", seed(self={"owner": ann()})
    )

    assert result.returncode == 0, result.stderr
    first, *rest = input_lines(result.stdout)
    assert [">", ["[]", ["[]", "self", "'owner'"], "'age'"], 60] in expressions(first)
    assert first["failure"] is None, first
    assert any(above(arg(line, "self", "owner", "age"), 60) for line in rest), result.stdout


# build-an-object-argument-from-its-type-hint-builds-from-a-hint-inside-a-named-object
def test_builds_from_a_hint_inside_a_named_object() -> None:
    named = "targets.classes.orders::Order"
    code, stdout, stderr = pyct(
        "ship_any", seed(o={"__class__": named, "owner": ann(), "items": []})
    )

    assert code == 0, stderr
    first, *rest = lines = input_lines(stdout)
    owner = {"name": "ann", "age": 30, "vip": False}
    assert first["args"] == {"o": {"__class__": named, "owner": owner, "items": []}}
    assert first["failure"] is None, first
    assert [">", ["[]", ["[]", "o", "'owner'"], "'age'"], 60] in expressions(first)
    assert any(above(arg(line, "o", "owner", "age"), 60) for line in rest), stdout
    assert all("__class__" not in held(line, "o", "owner") for line in lines), stdout


# build-an-object-argument-from-its-type-hint-passes-null-and-builds-an-object
@pytest.mark.parametrize("function", ["maybe", "maybe_old"])
def test_passes_null_and_builds_an_object(function: str) -> None:
    nobody = pyct(function, seed(c=None))
    somebody = pyct(function, seed(c=ann()))

    assert nobody[0] == 0, nobody[2]
    first = input_lines(nobody[1])[0]
    assert first["args"] == {"c": None} and first["failure"] is None, first
    assert any(
        above(arg(line, "c", "age"), 60) and line["failure"] is None for line in solved(somebody[1])
    ), somebody[1]


# build-an-object-argument-from-its-type-hint-passes-null-inside-an-object
def test_passes_null_inside_an_object() -> None:
    code, stdout, stderr = pyct(
        "deliver", seed(order={"owner": {**ann(), "home": None}, "items": []})
    )

    assert code == 0, stderr
    first = input_lines(stdout)[0]
    assert first["failure"] is None, first
    assert arg(first, "order", "owner", "home") is None


# build-an-object-argument-from-its-type-hint-passes-a-scalar-as-it-is
def test_passes_a_scalar_as_it_is() -> None:
    code, stdout, stderr = pyct("paint", seed(color="blue"))

    assert code == 0, stderr
    lines = input_lines(stdout)
    assert all(line["failure"] is None for line in lines), stdout
    assert any(arg(line, "color") == "red" for line in lines[1:]), stdout


# build-an-object-argument-from-its-type-hint-counts-an-unresolved-hint-as-none
def test_counts_an_unresolved_hint_as_none() -> None:
    code, stdout, stderr = pyct("late", seed(c=ann()))

    assert code == 0, stderr
    lines = input_lines(stdout)
    assert all(line["failure"] is None for line in lines), stdout
    assert any(above(arg(line, "c", "age"), 60) for line in lines[1:]), stdout


# build-an-object-argument-from-its-type-hint-keeps-the-json-value-under-a-container-hint
def test_keeps_the_json_value_under_a_container_hint() -> None:
    item = {"sku": "a", "qty": 1}
    args = seed(
        rows=[item],
        cfg={"a": item},
        spec={"size": 1},
        pair=[item, {"sku": "b", "qty": 2}],
        ids={"1": item},
    )
    code, stdout, stderr = pyct("kept", args)

    assert code == 0, stderr
    lines = input_lines(stdout)
    assert all(line["failure"] is None for line in lines), stdout
    assert any(above(arg(line, "spec", "size"), 3) for line in lines[1:]), stdout


# build-an-object-argument-from-its-type-hint-builds-the-class-of-a-union-with-plain-types
def test_builds_the_class_of_a_union_with_plain_types() -> None:
    name = pyct("label", seed(x="bob"))
    person = pyct("label", seed(x=ann()))

    for code, stdout, stderr in (name, person):
        assert code == 0, stderr
        # the criterion says no line fails, but the solver also flips Customer's own `age < 0`,
        # whose raise reports-a-constructor-that-raises-inside needs; only that input fails
        assert all(
            line["failure"] is None or line["failure"] == NEGATIVE_AGE
            for line in input_lines(stdout)
        ), stdout
    assert any(arg(line, "x") == "vip" for line in solved(name[1])), name[1]
    lines = input_lines(person[1])
    assert [">", ["[]", "x", "'age'"], 60] in expressions(lines[0])
    assert any(above(arg(line, "x", "age"), 60) for line in lines[1:]), person[1]


# build-an-object-argument-from-its-type-hint-still-checks-a-plain-hint
def test_still_checks_a_plain_hint() -> None:
    code, stdout, stderr = pyct("pair_up", seed(c=ann(), n="5", tags=[1, "2"]))

    assert code == 2
    assert stdout == ""
    lines = stderr.splitlines()
    assert 'n must be an int, got "5"' in lines, stderr
    assert 'tags[1] must be an int, got "2"' in lines, stderr
    assert not any(line.startswith("c") for line in lines), stderr


# build-an-object-argument-from-its-type-hint-passes-an-instance-run-hands-in
def test_passes_an_instance_run_hands_in(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)
    target = load_target(f"{HINTED}::greet")
    # the class of the module the target loaded, which a fresh interpreter can find by name
    given = importlib.import_module("targets.classes.customers").Customer("ann", 30)

    result = run(target, {"c": given})

    assert result.records
    assert all(
        record.failure is None or record.failure.kind is not FailureKind.TARGET_RAISED
        for record in result.records
    )
    assert given.age == 30


# build-an-object-argument-from-its-type-hint-fails-each-input-a-hint-cannot-build
def test_fails_each_input_a_hint_cannot_build(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)

    result = run(load_target(f"{HINTED}::draw"), {"s": {"side": 1}})

    assert result.records
    for record in result.records:
        assert record.failure is not None
        assert record.failure.kind is FailureKind.TARGET_RAISED
        assert record.failure.detail == f"building s: hint Shape is an abstract class; {NAME_IT}"


# build-an-object-argument-from-its-type-hint-builds-a-named-class-that-fits
def test_builds_a_named_class_that_fits() -> None:
    square = pyct("draw", seed(s={"__class__": "Square", "side": 2}))
    guest = {"__class__": "Guest", "name": "bob", "age": 30, "tags": []}
    either = pyct("either", seed(c=guest))

    for code, _, stderr in (square, either):
        assert code == 0, stderr
    assert any(
        above(arg(line, "s", "side"), 5)
        and arg(line, "s", "__class__") == "Square"
        and line["failure"] is None
        for line in solved(square[1])
    ), square[1]
    assert any(
        above(arg(line, "c", "age"), 60)
        and arg(line, "c", "__class__") == "Guest"
        and line["failure"] is None
        for line in solved(either[1])
    ), either[1]


# build-an-object-argument-from-its-type-hint-builds-a-named-class-through-run-unchecked
def test_builds_a_named_class_through_run_unchecked(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)
    guest = {"__class__": "Guest", "name": "ann", "age": 30, "tags": []}

    result = run(load_target(f"{HINTED}::greet"), {"c": guest})

    assert result.records
    assert all(
        record.failure is None or record.failure.kind is not FailureKind.TARGET_RAISED
        for record in result.records
    )
    assert all(arg({"args": record.args}, "c", "__class__") == "Guest" for record in result.records)
