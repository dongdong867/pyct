"""Acceptance tests for the list-a-package-s-entries story, one per criterion of sweep-a-package.

Every test spawns ``python -P -m pyct sweep ... --list`` from the repository root, so each
fixture package under ``targets/sweep/`` is named from ``targets``. stdout is one JSON line
per row, then the summary line, which a tool tells from a row by ``swept``.
"""

import importlib
import inspect
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.harness import REPO_ROOT

FIXTURES = "targets.sweep"


def sweep(
    *argv: str, env: dict[str, str] | None = None, timeout: float = 60
) -> subprocess.CompletedProcess[str]:
    """Spawn ``pyct sweep`` with ``argv``. ``env`` adds to or replaces the child's variables."""
    child = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    child.update(env or {})
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "sweep", *argv],
        cwd=REPO_ROOT,
        env=child,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def rows(stdout: str) -> list[dict[str, object]]:
    """The rows, without the summary line that closes stdout."""
    lines = [json.loads(line) for line in stdout.splitlines()]
    assert lines and "swept" in lines[-1], stdout
    return lines[:-1]


def summary(stdout: str) -> dict[str, object]:
    return json.loads(stdout.splitlines()[-1])


def row_named(stdout: str, module: str, name: str | None) -> dict[str, object]:
    found = [row for row in rows(stdout) if row["module"] == module and row["name"] == name]
    assert len(found) == 1, stdout
    return found[0]


def names(stdout: str) -> list[object]:
    return [row["name"] for row in rows(stdout)]


def error_of(call: Callable[[], object]) -> Exception:
    """What plain Python raises for ``call`` in this run, to compare a message with."""
    try:
        call()
    except Exception as error:
        return error
    raise AssertionError("the call raised nothing")


def as_json(value: object) -> str:
    """JSON text, which tells 0 from 0.0 and false where == does not."""
    return json.dumps(value)


# sweep-a-package-seeds-from-annotations
def test_seeds_from_annotations() -> None:
    result = sweep(f"{FIXTURES}.seeds", "--list")

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, f"{FIXTURES}.seeds", "f")
    assert row["status"] == "listed"
    expected = {"a": 0, "b": 0.0, "c": "", "d": False, "e": [], "g": {}, "h": 0, "i": ""}
    expected |= {"j": [], "k": "x", "m": None, "n": 0, "p": 0}
    assert as_json(row["seed"]) == as_json(expected)


# sweep-a-package-keeps-a-default-seed-json-carries
def test_keeps_a_default_seed_json_carries() -> None:
    result = sweep(f"{FIXTURES}.defaults", "--list")

    assert result.returncode == 0, result.stderr
    f = row_named(result.stdout, f"{FIXTURES}.defaults", "f")
    expected = {"x": 0, "strict": False, "sep": ",", "ratio": 0.5, "tags": ["a"]}
    assert as_json(f["seed"]) == as_json(expected)
    g = row_named(result.stdout, f"{FIXTURES}.defaults", "g")
    assert as_json(g["seed"]) == as_json({"value": 0, "strict": False})


# sweep-a-package-names-an-entry-by-the-file-that-holds-its-code
def test_names_an_entry_by_the_file_that_holds_its_code() -> None:
    shop = f"{FIXTURES}.shop"
    result = sweep(shop, "--list")

    assert result.returncode == 0, result.stderr
    assert row_named(result.stdout, f"{shop}._parse", "parse_price")["status"] == "listed"
    assert row_named(result.stdout, f"{shop}.prices", "total")["status"] == "listed"
    modules = {row["module"] for row in rows(result.stdout)}
    assert shop not in modules
    assert f"{shop}.catalog" not in modules


# sweep-a-package-lists-without-running
def test_lists_without_running(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    env = {"PATH": str(tmp_path / "no-cvc5-here"), "SWEEP_NOTE_FILE": str(note)}

    first = sweep(f"{FIXTURES}.writes", "--list", env=env)
    second = sweep(f"{FIXTURES}.writes", "--list", env=env)

    assert first.returncode == 0, first.stderr
    row = row_named(first.stdout, f"{FIXTURES}.writes.note", "jot")
    assert row["status"] == "listed"
    assert row["seed"] == {"n": 0}
    assert row["run"] is None
    assert not note.exists()
    assert summary(first.stdout)["stopped"] == "listed"
    assert second.returncode == 0, second.stderr
    assert second.stdout == first.stdout


# sweep-a-package-leaves-out-names-that-are-not-its-own
def test_leaves_out_names_that_are_not_its_own() -> None:
    result = sweep(f"{FIXTURES}.not_its_own", "--list")

    assert result.returncode == 0, result.stderr
    listed = names(result.stdout)
    for name in ("_helper", "RATE", "default_cart", "join", "sqrt"):
        assert name not in listed


# sweep-a-package-follows-all
def test_follows_all() -> None:
    result = sweep(f"{FIXTURES}.follows_all", "--list")

    assert result.returncode == 0, result.stderr
    assert names(result.stdout) == ["_b", "a"]


# sweep-a-package-walks-public-modules
def test_walks_public_modules() -> None:
    walk = f"{FIXTURES}.walk"
    result = sweep(walk, "--list")
    internal = sweep(f"{walk}._internal", "--list")

    assert result.returncode == 0, result.stderr
    named = [(row["module"], row["name"]) for row in rows(result.stdout)]
    assert named == [(f"{walk}.prices", "total"), (f"{walk}.util.text", "shout")]
    assert internal.returncode == 0, internal.stderr
    assert [row["name"] for row in rows(internal.stdout)] == ["audit"]


# sweep-a-package-looks-through-decorators
def test_looks_through_decorators() -> None:
    result = sweep(f"{FIXTURES}.wrapped", "--list")

    assert result.returncode == 0, result.stderr
    total = row_named(result.stdout, f"{FIXTURES}.wrapped.prices", "total")
    fetch = row_named(result.stdout, f"{FIXTURES}.wrapped.prices", "fetch")
    assert (total["status"], total["seed"]) == ("listed", {"n": 0})
    assert (fetch["status"], fetch["seed"]) == ("listed", {"key": 0})


# sweep-a-package-lists-methods-as-skipped
def test_lists_methods_as_skipped() -> None:
    module = f"{FIXTURES}.methods"
    result = sweep(module, "--list")

    assert result.returncode == 0, result.stderr
    cart = row_named(result.stdout, module, "Cart")
    special = row_named(result.stdout, module, "Special")
    assert (cart["status"], cart["seed"]) == ("listed", {"owner": ""})
    assert (special["status"], special["seed"]) == ("listed", {"owner": ""})
    for name in ("Cart.empty", "Cart.rate", "Cart.total", "Parser.parse"):
        row = row_named(result.stdout, module, name)
        assert (row["status"], row["seed"]) == ("skipped", None)
        assert row["reason"] == "pyct run cannot call a method yet"
    expected = ["Cart", "Cart.empty", "Cart.rate", "Cart.total", "Parser.parse", "Special"]
    assert names(result.stdout) == expected


# sweep-a-package-skips-an-entry-it-cannot-seed
def test_skips_an_entry_it_cannot_seed() -> None:
    module = f"{FIXTURES}.cannot_seed"
    result = sweep(module, "--list")

    assert result.returncode == 0, result.stderr
    reasons = {row["name"]: row["reason"] for row in rows(result.stdout)}
    assert reasons["main"] == "no parameter to vary"
    assert reasons["only"] == "no parameter to vary"
    assert reasons["later"] == "no parameter to vary"
    assert reasons["load"] == "no seed for data: bytes"
    assert reasons["pair"] == "no seed for t: tuple[int, int]"
    plain = error_of(lambda: inspect.signature(importlib.import_module(module).odd))
    assert reasons["odd"] == f"cannot read the signature: {plain}"
    assert summary(result.stdout)["skipped"] == 6


# sweep-a-package-skips-code-no-module-names
def test_skips_code_no_module_names() -> None:
    generated = f"{FIXTURES}.generated"
    result = sweep(generated, "--list")

    assert result.returncode == 0, result.stderr
    made = row_named(result.stdout, f"{generated}.api", "made")
    parse = row_named(result.stdout, f"{generated}.api", "parse")
    assert (made["status"], made["reason"]) == ("skipped", "generated code")
    assert parse["status"] == "skipped"
    assert parse["reason"] == f"no name in {generated}.factory holds it"


# sweep-a-package-reads-text-annotations
def test_reads_text_annotations() -> None:
    result = sweep(f"{FIXTURES}.text_annotations", "--list")

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, f"{FIXTURES}.text_annotations", "f")
    assert as_json(row["seed"]) == as_json({"a": 0, "b": [], "c": 0})


# sweep-a-package-prints-only-the-summary-when-nothing-is-found
def test_prints_only_the_summary_when_nothing_is_found() -> None:
    module = f"{FIXTURES}.nothing"
    result = sweep(module, "--list")

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 1
    line = summary(result.stdout)
    assert line["swept"] == module
    assert [line[count] for count in ("ran", "failed", "skipped", "listed")] == [0, 0, 0, 0]
    assert f"found no entries in {module}" in result.stderr.splitlines()


# sweep-a-package-reports-a-module-that-does-not-import
def test_reports_a_module_that_does_not_import() -> None:
    rough = f"{FIXTURES}.rough"
    result = sweep(rough, "--list")

    assert result.returncode == 0, result.stderr
    broken = row_named(result.stdout, f"{rough}.broken", None)
    assert broken == {
        "module": f"{rough}.broken",
        "name": None,
        "status": "failed",
        "seed": None,
        "reason": f"cannot import {rough}.broken: ValueError('boom')",
        "run": None,
    }
    gone = row_named(result.stdout, f"{rough}.gone", None)
    assert gone["reason"] == f"cannot import {rough}.gone: ValueError('boom')"
    assert not [row for row in rows(result.stdout) if row["module"] == f"{rough}.gone.inner"]
    assert row_named(result.stdout, f"{rough}.prices", "total")["status"] == "listed"


# sweep-a-package-outlives-a-module-that-ends-its-process
def test_outlives_a_module_that_ends_its_process() -> None:
    rough = f"{FIXTURES}.rough"
    result = sweep(rough, "--list")

    assert result.returncode == 0, result.stderr
    failed = {row["reason"] for row in rows(result.stdout) if row["status"] == "failed"}
    assert f"cannot import {rough}.crashes: killed by SIGSEGV" in failed
    assert f"cannot import {rough}.exits: exited with code 3" in failed
    assert f"cannot import {rough}.quits: SystemExit(0)" in failed
    assert row_named(result.stdout, f"{rough}.zeta", "last")["status"] == "listed"


# sweep-a-package-stops-an-import-that-hangs
@pytest.mark.timeout(180)
def test_stops_an_import_that_hangs(tmp_path: Path) -> None:
    stall = f"{FIXTURES}.stall"
    pids_file = tmp_path / "pids"
    result = sweep(stall, "--list", env={"SWEEP_PIDS_FILE": str(pids_file)}, timeout=170)

    assert result.returncode == 0, result.stderr
    hangs = row_named(result.stdout, f"{stall}.hangs", None)
    assert hangs["reason"] == f"cannot import {stall}.hangs: did not finish in 60 s"
    assert row_named(result.stdout, f"{stall}.zeta", "last")["status"] == "listed"
    for pid in pids_file.read_text().split():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


# sweep-a-package-stops-when-the-package-does-not-import
def test_stops_when_the_package_does_not_import() -> None:
    missing = sweep("no_such_package", "--list")
    fails = sweep(f"{FIXTURES}.fails", "--list")

    with pytest.raises(ModuleNotFoundError) as plain:
        importlib.import_module("no_such_package")
    assert missing.returncode == 1
    assert missing.stdout == ""
    assert f"cannot import no_such_package: {plain.value!r}" in missing.stderr.splitlines()
    assert fails.returncode == 1
    assert fails.stdout == ""
    assert f"cannot import {FIXTURES}.fails: ValueError('boom')" in fails.stderr.splitlines()
