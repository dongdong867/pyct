"""Acceptance tests for an-llm-seed-names-an-object-s-class: an LLM seed whose class pyct refuses,
or that fails a seed check, is dropped, and the run goes on with its other seeds.

The ``pyct run`` cases point the provider's base URLs at the stub on localhost; the one ``run()``
case answers with a fake ``SeedProvider``.
"""

import importlib
import inspect
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.notes import Note, SeedDropped, SeedsKept
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from pyct.run.tell import Tell
from tests.acceptance.fake_seeds import replying
from tests.acceptance.harness import input_lines
from tests.acceptance.llm_stub import Stub, heads, llm_run, sources

M = "targets.llm.shop.models"
GREET = "targets.llm.shop.greet::greet"
ANN = {"__class__": f"{M}::Customer", "name": "ann", "age": 30}
# the user's seed of builds-and-follows-an-object
OWN = json.dumps({"c": ANN})
LIBRARY = "c['__class__'] must name a class of the user's own code, got"


def greet_with(
    stub: Stub, tmp_path: Path, reply: Sequence[object], *own: str
) -> CompletedProcess[str]:
    """``pyct run`` of greet with the user's seeds ``own`` and the LLM's ``reply``."""
    stub.reply = json.dumps(reply)
    return llm_run(stub.port, tmp_path, *own, "--llm", "seeds", target=GREET)


def is_solver(line: dict[str, object]) -> bool:
    return line["source"] == "solver"


# llm-seed-class-refused-skipped-skips-a-library-s-class
def test_a_seed_naming_a_library_s_class_is_dropped(stub: Stub, tmp_path: Path) -> None:
    own = json.dumps({"c": {**ANN, "name": "bob", "age": 1}})
    popen = {"c": {"__class__": "subprocess::Popen", "args": ["true"]}}
    date = {"c": {"__class__": "datetime::date", "year": 2024, "month": 1, "day": 1}}

    result = greet_with(stub, tmp_path, [popen, date, {"c": ANN}], own)

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    assert f'llm: dropped seed 1: {LIBRARY} "subprocess::Popen"' in lines
    assert f'llm: dropped seed 2: {LIBRARY} "datetime::date"' in lines
    assert heads(result.stderr)[:2] == [f"seed {own}", f"llm seed 3 {json.dumps({'c': ANN})}"]
    assert sources(result.stdout).count("llm_seed") == 1


# llm-seed-class-refused-skipped-imports-nothing-it-skips
def test_a_dropped_seed_s_module_is_never_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "tabnanny", raising=False)
    notes: list[Note] = []
    provider = replying({"c": {"__class__": "tabnanny::NannyNag"}}, {"c": ANN})
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))

    result = run(load_target(GREET), [], setup=setup, tell=Tell(noted=notes.append))

    assert notes[:2] == [SeedDropped(1, f'{LIBRARY} "tabnanny::NannyNag"'), SeedsKept((2,))]
    assert result.records[0].args == {"c": ANN}
    assert "tabnanny" not in sys.modules


# llm-seed-class-refused-skipped-skips-a-library-s-class-through-the-user-s-module
def test_a_library_s_class_named_through_the_user_s_module_is_dropped(
    stub: Stub, tmp_path: Path
) -> None:
    date = {"__class__": "targets.llm.shop.greet::date", "year": 2024, "month": 1, "day": 1}

    result = greet_with(stub, tmp_path, [{"c": date}], OWN)

    assert result.returncode == 0, result.stderr
    said = f'llm: dropped seed 1: {LIBRARY} "targets.llm.shop.greet::date"'
    assert said in result.stderr.splitlines()


# llm-seed-class-refused-skipped-skips-a-module-the-request-did-not-list
def test_a_class_in_a_module_the_request_did_not_list_is_dropped(
    stub: Stub, tmp_path: Path
) -> None:
    result = greet_with(
        stub, tmp_path, [{"c": {"__class__": "targets.classes.orders::Buyer"}}], OWN
    )

    assert result.returncode == 0, result.stderr
    said = (
        "llm: dropped seed 1: c['__class__'] must name a class the request listed or one already"
        ' imported, got "targets.classes.orders::Buyer"'
    )
    assert said in result.stderr.splitlines()


# llm-seed-class-refused-skipped-skips-a-module-the-request-did-not-list
def test_a_class_in_the_package_s_main_is_dropped_and_never_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = "targets.llm.shop.__main__"
    monkeypatch.delitem(sys.modules, main, raising=False)
    notes: list[Note] = []
    provider = replying({"c": {"__class__": f"{main}::Runner", "name": "x"}}, {"c": ANN})
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))

    run(load_target(GREET), [], setup=setup, tell=Tell(noted=notes.append))

    said = (
        "c['__class__'] must name a class the request listed or one already imported, got"
        f' "{main}::Runner"'
    )
    assert notes[:2] == [SeedDropped(1, said), SeedsKept((2,))]
    assert main not in sys.modules


# llm-seed-class-refused-skipped-skips-a-class-pyct-cannot-find
def test_a_seed_naming_a_class_pyct_cannot_find_is_dropped(stub: Stub, tmp_path: Path) -> None:
    reply = [
        {"c": {**ANN, "__class__": f"{M}::Client"}},
        {"c": {"__class__": f"{M}::Desk.serve"}},
        {"c": {**ANN, "__class__": f"{M}:Customer"}},
    ]

    result = greet_with(stub, tmp_path, reply, OWN)

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    assert f"llm: dropped seed 1: c['__class__']: {M} has no class Client" in lines
    assert f"llm: dropped seed 2: c['__class__']: {M}::Desk.serve is not a class" in lines
    said = "llm: dropped seed 3: c['__class__'] must be MODULE::CLASS or a class name, got"
    assert f'{said} "{M}:Customer"' in lines
    assert sources(result.stdout)[0] == "seed"
    assert "llm_seed" not in sources(result.stdout)
    assert any(is_solver(line) for line in input_lines(result.stdout))


# llm-seed-class-refused-skipped-skips-a-seed-a-user-s-check-refuses
def test_a_seed_a_user_s_seed_check_refuses_is_dropped(stub: Stub, tmp_path: Path) -> None:
    customer = importlib.import_module(M).Customer
    with pytest.raises(TypeError) as plain:
        inspect.signature(customer).bind(name="ann")
    reason = str(plain.value)
    no_age = {"__class__": f"{M}::Customer", "name": "ann"}
    reply = [{"c": no_age}, {"c": {**ANN, "__calls__": []}}]

    result = greet_with(stub, tmp_path, reply, OWN)

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    assert f"llm: dropped seed 1: c (name) does not fit Customer(name, age): {reason}" in lines
    said = "llm: dropped seed 2: c cannot hold '__calls__': pyct reserves keys that start and end"
    assert f"{said} with __" in lines


# llm-seed-class-refused-skipped-runs-a-seed-whose-constructor-raises
def test_a_seed_whose_constructor_raises_runs_and_reports_the_raise(
    stub: Stub, tmp_path: Path
) -> None:
    result = greet_with(stub, tmp_path, [{"c": {**ANN, "age": -1}}])

    assert result.returncode == 0, result.stderr
    assert not [line for line in result.stderr.splitlines() if "llm: dropped seed" in line]
    first, *rest = input_lines(result.stdout)
    assert first["source"] == "llm_seed"
    assert first["failure"] == {
        "kind": "target_raised",
        "detail": "building c: ValueError: negative age",
    }
    assert any(
        is_solver(line) and line["failure"] is None and line["args"]["c"]["age"] >= 0  # pyrefly: ignore
        for line in rest
    ), rest


# llm-seed-class-refused-skipped-refuses-a-run-left-with-no-seed
def test_a_run_whose_every_llm_seed_is_dropped_and_has_none_of_its_own_is_refused(
    stub: Stub, tmp_path: Path
) -> None:
    popen = {"c": {"__class__": "subprocess::Popen", "args": ["true"]}}

    result = greet_with(stub, tmp_path, [popen])

    assert result.returncode == 1
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    dropped = lines.index(f'llm: dropped seed 1: {LIBRARY} "subprocess::Popen"')
    assert lines[dropped + 1] == "no seed: the LLM gave none (every seed was dropped)"
