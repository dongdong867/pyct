"""Acceptance tests for run-a-plain-dict-stays-a-dict: a dict the seed gave as a plain dict
stays a dict in every input the solver writes, and each line writes its key ``"__class__"`` as
``"!__class__"``.

Each test spawns ``python -P -m pyct`` through the harness, or calls ``run()``, on the target
functions of ``targets/dicts/class_key.py``. The LLM cases are in the ``_llm`` file beside this.
"""

import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from pyct.results.record import InputRecord, Source
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from targets.classes import customers
from targets.dicts import class_key
from tests.acceptance.harness import forks_of, input_lines, run_pyct

M = "targets.dicts.class_key"
BOX = f"{M}::Box"
HAS_CLASS = ["in", "'__class__'", "d"]
IN_PROCESS = Setup(isolation=Isolation.IN_PROCESS)


def line_of(function: Callable[..., object], text: str) -> int:
    """The line of a function's source that holds ``text``."""
    source, start = inspect.getsourcelines(function)
    return next(start + at for at, line in enumerate(source) if text in line)


def returns_1(function: Callable[..., object]) -> int:
    return line_of(function, "return 1")


def covers(line: Mapping[str, object], number: int) -> bool:
    """Whether a printed line covers line ``number`` of ``class_key.py``."""
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return any(
        path.endswith("targets/dicts/class_key.py") and number in lines
        for path, lines in covered.items()
    )


def an_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def took(line: Mapping[str, object], expression: object) -> bool | None:
    """Which way a printed line took the fork on ``expression``, or None when it has none."""
    sides = [fork["taken"] for fork in forks_of(dict(line)) if fork["expression"] == expression]
    return bool(sides[0]) if sides else None


def plain_with(args: object, *path: object) -> tuple[dict[object, object], object]:
    """The dict ``args`` holds at ``path``, without its ``"!__class__"``, and that key's value;
    an empty dict and None when ``args`` holds no dict there."""
    for step in path:
        try:
            args = args[step]  # pyrefly: ignore[bad-index]
        except (IndexError, KeyError, TypeError):
            return {}, None
    if not isinstance(args, dict):
        return {}, None
    rest = {key: value for key, value in args.items() if key != "!__class__"}
    return rest, args.get("!__class__")


def solver_lines(stdout: str) -> list[dict[str, object]]:
    return [line for line in input_lines(stdout) if line["source"] == "solver"]


def escaped_line(
    stdout: str, path: Sequence[object], rest: dict[object, object]
) -> dict[str, object]:
    """The first solver line whose dict at ``path`` is ``rest`` and an int under
    ``"!__class__"``, with no failure."""
    for line in solver_lines(stdout):
        held, value = plain_with(line["args"], *path)
        if held == rest and an_int(value) and line["failure"] is None:
            return line
    raise AssertionError(stdout)


def pyct(target: str, args: object) -> tuple[int, str, str]:
    result = run_pyct(f"{M}::{target}", "--args", json.dumps(args))
    return result.returncode, result.stdout, result.stderr


def run_records(target: str, seed: Mapping[str, object]) -> list[InputRecord]:
    return list(run(load_target(f"{M}::{target}"), seed, setup=IN_PROCESS).records)


# run-a-plain-dict-stays-a-dict-when-the-solver-adds-the-class-key
def test_when_the_solver_adds_the_class_key() -> None:
    code, stdout, stderr = pyct("has_class", {"d": {"a": 1}})

    assert code == 0, stderr
    assert took(input_lines(stdout)[0], HAS_CLASS) is False
    line = escaped_line(stdout, ["d"], {"a": 1})
    assert took(line, HAS_CLASS) is True
    assert covers(line, returns_1(class_key.has_class))


# run-a-plain-dict-stays-a-dict-when-the-solver-names-a-class
def test_when_the_solver_names_a_class() -> None:
    code, stdout, stderr = pyct("names_box", {"d": {"a": "x"}})

    assert code == 0, stderr
    named = {"d": {"a": "x", "!__class__": BOX}}
    lines = [line for line in solver_lines(stdout) if line["args"] == named]
    assert lines, stdout
    assert lines[0]["failure"] is None
    assert covers(lines[0], returns_1(class_key.names_box))


# run-a-plain-dict-stays-a-dict-inside-a-list
def test_inside_a_list() -> None:
    code, stdout, stderr = pyct("first_has_class", {"xs": [{"a": 1}]})

    assert code == 0, stderr
    line = escaped_line(stdout, ["xs", 0], {"a": 1})
    xs = line["args"]["xs"]  # pyrefly: ignore[bad-index]
    assert isinstance(xs, list) and len(xs) == 1, line
    assert covers(line, returns_1(class_key.first_has_class))


# run-a-plain-dict-stays-a-dict-inside-an-object
def test_inside_an_object() -> None:
    code, stdout, stderr = pyct("box_has_class", {"b": {"__class__": BOX, "d": {"a": 1}}})

    assert code == 0, stderr
    line = escaped_line(stdout, ["b", "d"], {"a": 1})
    held, _ = plain_with(line["args"], "b")
    assert (set(held), held["__class__"]) == ({"__class__", "d"}, BOX), line
    assert covers(line, returns_1(class_key.box_has_class))


# run-a-plain-dict-stays-a-dict-under-self
def test_under_self() -> None:
    code, stdout, stderr = pyct("Holder.has", {"self": {"d": {"a": 1}}})

    assert code == 0, stderr
    line = escaped_line(stdout, ["self", "d"], {"a": 1})
    assert list(line["args"]["self"]) == ["d"]  # pyrefly: ignore[bad-index]
    assert covers(line, line_of(class_key.Holder.has, "return 1"))


# run-a-plain-dict-stays-a-dict-inside-a-tuple-through-run
def test_inside_a_tuple_through_run() -> None:
    records = run_records("pair_has_class", {"pair": ({"a": 1}, 0)})

    found = [
        record
        for record in records
        if record.source is Source.SOLVER
        and record.failure is None
        and isinstance(pair := record.args["pair"], tuple)
        and len(pair) == 2
        and pair[1] == 0
        and plain_with(pair, 0)[0] == {"a": 1}
        and an_int(plain_with(pair, 0)[1])
    ]
    assert found, records
    assert returns_1(class_key.pair_has_class) in found[0].covered_lines


# run-a-plain-dict-stays-a-dict-through-run
def test_through_run() -> None:
    first = run_records("has_class", {"d": {"a": 1}})
    covering = [
        record
        for record in first
        if record.source is Source.SOLVER and returns_1(class_key.has_class) in record.covered_lines
    ]
    assert covering, first
    args = covering[0].args

    again = run_records("has_class", args)

    held, value = plain_with(args, "d")
    assert held == {"a": 1} and an_int(value), args
    assert again[0].failure is None, again[0].failure
    assert returns_1(class_key.has_class) in again[0].covered_lines


# run-a-plain-dict-stays-a-dict-when-a-line-runs-again
def test_when_a_line_runs_again() -> None:
    code, stdout, stderr = pyct("has_class", {"d": {"a": 1}})
    assert code == 0, stderr
    taken = [line for line in solver_lines(stdout) if took(line, HAS_CLASS) is True]
    assert taken, stdout

    code, again, stderr = pyct("has_class", taken[0]["args"])

    assert code == 0, stderr
    seed = input_lines(again)[0]
    assert seed["args"] == taken[0]["args"]
    assert took(seed, HAS_CLASS) is True
    assert seed["failure"] is None


# run-a-plain-dict-stays-a-dict-from-a-seed-s-escaped-key
def test_from_a_seed_s_escaped_key() -> None:
    code, stdout, stderr = pyct("has_class", {"d": {"!__class__": 1}})

    assert code == 0, stderr
    seed = input_lines(stdout)[0]
    assert (seed["args"], seed["failure"]) == ({"d": {"!__class__": 1}}, None)
    assert took(seed, HAS_CLASS) is True
    assert any(
        "!__class__" not in line["args"]["d"] and took(line, HAS_CLASS) is False  # pyrefly: ignore[bad-index]
        for line in solver_lines(stdout)
    ), stdout


# run-a-plain-dict-stays-a-dict-escapes-an-escaped-key
def test_escapes_an_escaped_key() -> None:
    code, stdout, stderr = pyct("has_escaped", {"d": {"a": 1}})
    given_code, given, given_stderr = pyct("has_escaped", {"d": {"!__class__": 1}})

    assert code == 0, stderr
    lines = [
        line
        for line in solver_lines(stdout)
        if line["failure"] is None
        and set(line["args"]["d"]) == {"a", "!!__class__"}  # pyrefly: ignore[bad-index]
        and line["args"]["d"]["a"] == 1  # pyrefly: ignore[bad-index]
        and an_int(line["args"]["d"]["!!__class__"])  # pyrefly: ignore[bad-index]
    ]
    assert lines, stdout
    assert covers(lines[0], returns_1(class_key.has_escaped))
    assert given_code == 0, given_stderr
    first = input_lines(given)[0]
    assert first["failure"] is None, first
    assert not covers(first, returns_1(class_key.has_escaped)), first
    assert covers(first, line_of(class_key.has_escaped, "return 0")), first


# run-a-plain-dict-stays-a-dict-around-a-built-object
def test_around_a_built_object() -> None:
    seed = {"box": {"!__class__": 0, "b": {"__class__": BOX, "d": 1}}}

    code, stdout, stderr = pyct("holds_a_box", seed)

    assert code == 0, stderr
    first = input_lines(stdout)[0]
    assert first["failure"] is None, first
    assert covers(first, returns_1(class_key.holds_a_box))


# run-a-plain-dict-stays-a-dict-reads-old-seeds-as-before
def test_reads_old_seeds_as_before(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text(
        json.dumps({"d": {"__class__": BOX, "d": {}}})
        + "\n"
        + json.dumps({"d": {"__complex__": True}})
        + "\n"
    )

    result = run_pyct(f"{M}::kind_of", "--seeds", str(seeds))

    assert result.returncode == 0, result.stderr
    built, plain = input_lines(result.stdout)[:2]
    assert (built["failure"], plain["failure"]) == (None, None)
    assert covers(built, returns_1(class_key.kind_of))
    assert covers(plain, line_of(class_key.kind_of, "return 0"))


def fit_reason(cls: type, **fields: object) -> str:
    """What plain Python says, in this run, binding ``fields`` to ``cls``'s signature."""
    with pytest.raises(TypeError) as plain:
        inspect.signature(cls).bind(**fields)
    return str(plain.value)


# run-a-plain-dict-stays-a-dict-refuses-an-escaped-key-in-an-object
def test_refuses_an_escaped_key_in_an_object() -> None:
    fields = {"name": "ann", "age": 30, "!__class__": 0}

    result = run_pyct(
        "targets.classes.greet::greet",
        "--args",
        json.dumps({"c": {"__class__": "Customer", **fields}}),
    )

    reason = fit_reason(customers.Customer, **fields)
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        f"c (name, age, !__class__) does not fit Customer(name, age, vip): {reason}"
    ]
