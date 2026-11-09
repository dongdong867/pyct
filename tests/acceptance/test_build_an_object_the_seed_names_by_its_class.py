"""Acceptance tests for build-an-object-the-seed-names-by-its-class.

Each test spawns ``python -P -m pyct`` through the harness, or calls ``run()``, on the target
functions of ``targets/classes/greet.py`` and the classes of ``targets/classes/customers.py``,
whose seeds name each object's class with ``"__class__"``.
"""

import importlib
import inspect
import json
from collections.abc import Callable

import pytest

from pyct.results.failure import FailureKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from targets.classes import customers
from tests.acceptance.harness import (
    forks_of,
    input_lines,
    let_pyct_run_in_process,
    lines_expressions_and_sides,
    run_pyct,
)

GREET = "targets.classes.greet"
CUSTOMERS = "targets.classes.customers"
AGE = ["[]", "c", "'age'"]
AGE_ABOVE_60 = [">", AGE, 60]


def seed(**args: object) -> str:
    return json.dumps(args)


def customer(cls: str = "Customer", age: int = 30) -> dict[str, object]:
    return {"__class__": cls, "name": "ann", "age": age}


def arg(line: dict[str, object], *path: object) -> object:
    """The value a printed line's ``args`` holds at ``path``."""
    value: object = line["args"]
    for step in path:
        assert isinstance(value, dict | list), line
        value = value[step]  # pyrefly: ignore[bad-index]
    return value


def above(value: object, bound: int) -> bool:
    """Whether a value off a printed line is an int above ``bound``."""
    return isinstance(value, int) and not isinstance(value, bool) and value > bound


def below_zero(value: object) -> bool:
    """Whether a value off a printed line is an int below 0."""
    return isinstance(value, int) and not isinstance(value, bool) and value < 0


def solved(stdout: str) -> list[dict[str, object]]:
    """The input lines after the seed's."""
    return input_lines(stdout)[1:]


def line_of(function: Callable[..., object], text: str) -> int:
    """The line of a function's source that holds ``text``."""
    source, start = inspect.getsourcelines(function)
    return next(start + at for at, line in enumerate(source) if text in line)


def import_raise(module: str) -> BaseException:
    """What plain Python's import of ``module`` raises in this run."""
    try:
        importlib.import_module(module)
    except Exception as error:
        return error
    raise AssertionError(f"{module} imported")


# build-an-object-the-seed-names-by-its-class-finds-a-bare-name-in-the-target-s-module
def test_finds_a_bare_name_in_the_target_s_module() -> None:
    result = run_pyct(f"{GREET}::greet", "--args", seed(c=customer()))

    assert result.returncode == 0, result.stderr
    older = [
        line
        for line in solved(result.stdout)
        if above(arg(line, "c", "age"), 60) and line["failure"] is None
    ]
    assert older, result.stdout


# build-an-object-the-seed-names-by-its-class-builds-any-kind-of-class
def test_builds_any_kind_of_class() -> None:
    profile = run_pyct(f"{GREET}::older", "--args", seed(p={"__class__": "Profile", "age": 30}))
    pair = run_pyct(
        f"{GREET}::left_is_big", "--args", seed(q={"__class__": "Pair", "left": 1, "right": 2})
    )
    date = {"__class__": "datetime::date", "year": 2024, "month": 1, "day": 1}
    dated = run_pyct(f"{GREET}::is_a_date", "--args", seed(d=date))

    for result in (profile, pair, dated):
        assert result.returncode == 0, result.stderr
    assert any(above(arg(line, "p", "age"), 60) for line in solved(profile.stdout))
    assert any(above(arg(line, "q", "left"), 5) for line in solved(pair.stdout))
    assert input_lines(dated.stdout)[0]["failure"] is None, dated.stdout


# build-an-object-the-seed-names-by-its-class-builds-each-input-its-own-object
def test_builds_each_input_its_own_object() -> None:
    args = seed(c=customer(f"{CUSTOMERS}::Customer"))
    result = run_pyct(f"{GREET}::visit", "--args", args, "--in-process")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the criterion says no line fails, but the solver also flips Customer's own `age < 0`,
    # whose raise reports-a-constructor-that-raises needs; only that input fails, never the
    # target's raise for an object a second input reused
    negative = {"kind": "target_raised", "detail": "building c: ValueError: negative age"}
    failed = [line for line in lines if line["failure"] is not None]
    assert all(line["failure"] == negative for line in failed), result.stdout
    assert all(below_zero(arg(line, "c", "age")) for line in failed), result.stdout
    assert any(above(arg(line, "c", "age"), 60) for line in lines[1:]), result.stdout


# build-an-object-the-seed-names-by-its-class-keeps-an-object-without-a-class-a-dict
def test_keeps_an_object_without_a_class_a_dict() -> None:
    result = run_pyct(f"{GREET}::kind_of", "--args", seed(d={"__args__": [1], "k": 0}))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert all(line["failure"] is None for line in lines), result.stdout
    assert any(above(arg(line, "d", "k"), 1) for line in lines[1:]), result.stdout


# build-an-object-the-seed-names-by-its-class-passes-args-by-position
def test_passes_args_by_position() -> None:
    point = seed(p={"__class__": "Point", "__args__": [1], "y": 2})
    placed = run_pyct(f"{GREET}::placed", "--args", point)
    path = seed(f={"__class__": "pathlib::Path", "__args__": ["a/b"]})
    suffixed = run_pyct(f"{GREET}::suffix_of", "--args", path)

    assert placed.returncode == 0, placed.stderr
    assert suffixed.returncode == 0, suffixed.stderr
    first = ["[]", ["[]", "p", "'__args__'"], 0]
    assert [fork["expression"] for fork in forks_of(input_lines(placed.stdout)[0])] == [
        [">", first, 5]
    ]
    forks = [line for line in placed.stderr.splitlines() if line.startswith("fork ")]
    assert any("  p['__args__'][0] > 5  " in line for line in forks), placed.stderr
    assert any(
        above(arg(line, "p", "__args__", 0), 5) and arg(line, "p", "y") == 2
        for line in solved(placed.stdout)
    ), placed.stdout
    assert input_lines(suffixed.stdout)[0]["failure"] is None, suffixed.stdout


# build-an-object-the-seed-names-by-its-class-builds-an-object-inside-an-object
def test_builds_an_object_inside_an_object() -> None:
    order = {"__class__": "Order", "customer": customer(), "total": 5}
    result = run_pyct(f"{GREET}::ship", "--args", seed(o=order))

    assert result.returncode == 0, result.stderr
    first = input_lines(result.stdout)[0]
    inner_age = ["[]", ["[]", "o", "'customer'"], "'age'"]
    assert [fork["expression"] for fork in forks_of(first)] == [
        ["<", inner_age, 0],
        [">", inner_age, 60],
    ]
    assert first["failure"] is None
    assert any(above(arg(line, "o", "customer", "age"), 60) for line in solved(result.stdout))


# build-an-object-the-seed-names-by-its-class-builds-an-object-inside-self
def test_builds_an_object_inside_self() -> None:
    result = run_pyct(f"{CUSTOMERS}::Shop.serve", "--args", seed(self={"owner": customer()}))

    assert result.returncode == 0, result.stderr
    first = input_lines(result.stdout)[0]
    owner_age = ["[]", ["[]", "self", "'owner'"], "'age'"]
    assert [">", owner_age, 60] in [fork["expression"] for fork in forks_of(first)]
    assert first["failure"] is None
    assert any(above(arg(line, "self", "owner", "age"), 60) for line in solved(result.stdout)), (
        result.stdout
    )


# build-an-object-the-seed-names-by-its-class-keeps-an-object-s-keys-and-args
def test_keeps_an_object_s_keys_and_args() -> None:
    tags = {"__class__": "Tags", "__args__": ["a"], "colour": "red"}
    result = run_pyct(f"{GREET}::label", "--args", seed(t=tags))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    for line in lines:
        held = arg(line, "t")
        assert isinstance(held, dict) and list(held) == ["__class__", "__args__", "colour"]
        assert isinstance(held["__args__"], list) and len(held["__args__"]) == 1
    assert any(arg(line, "t", "__args__", 0) == "x" for line in lines[1:]), result.stdout


# build-an-object-the-seed-names-by-its-class-writes-an-input-that-runs-again
def test_writes_an_input_that_runs_again() -> None:
    spec = f"{GREET}::greet"
    older = next(
        line
        for line in solved(run_pyct(spec, "--args", seed(c=customer())).stdout)
        if above(arg(line, "c", "age"), 60)
    )

    again = run_pyct(spec, "--args", json.dumps(older["args"]))

    assert again.returncode == 0, again.stderr
    assert arg(older, "c", "__class__") == "Customer"
    seed_line = input_lines(again.stdout)[0]
    assert seed_line["args"] == older["args"]
    assert lines_expressions_and_sides(seed_line) == lines_expressions_and_sides(older)


# build-an-object-the-seed-names-by-its-class-reports-a-constructor-that-raises
def test_reports_a_constructor_that_raises() -> None:
    result = run_pyct(f"{GREET}::greet", "--args", seed(c=customer(age=-1)))

    assert result.returncode == 0, result.stderr
    first, *rest = input_lines(result.stdout)
    negative = (line_of(customers.Customer.__init__, "age < 0"), ["<", AGE, 0], True)
    assert negative in lines_expressions_and_sides(first), result.stdout
    detail = "building c: ValueError: negative age"
    assert first["failure"] == {"kind": "target_raised", "detail": detail}
    assert f"ended target raised: {detail}" in result.stderr.splitlines(), result.stderr
    built = [
        line
        for line in rest
        if line["failure"] is None
        and isinstance(arg(line, "c", "age"), int)
        and not below_zero(arg(line, "c", "age"))
        and AGE_ABOVE_60 in [fork["expression"] for fork in forks_of(line)]
    ]
    assert built, result.stdout


# build-an-object-the-seed-names-by-its-class-fails-an-object-run-cannot-build
@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.IN_PROCESS, Isolation.FRESH])
def test_fails_an_object_run_cannot_build(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    let_pyct_run_in_process(monkeypatch)
    missing = "targets.classes.nowhere"
    target = load_target(f"{GREET}::greet")

    result = run(target, {"c": customer(f"{missing}::Customer")}, isolation=isolation)

    record = result.records[0]
    assert record.failure is not None
    assert record.failure.kind is FailureKind.TARGET_RAISED
    assert (
        record.failure.detail == f"building c: cannot import {missing}: {import_raise(missing)!r}"
    )
    assert record.forks == ()
