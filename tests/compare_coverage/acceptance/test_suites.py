"""Acceptance tests for compare-coverage-on-legacys-suites: legacy's examples and libraries.

The examples run in place in a real checkout of main, and the realworld entries name the
library version each side imported. Every set runs through the command line's own
preparation with sides that answer at once. A library missing on one side, or at another
version there, runs against the stub engine with a library only the stub has.
"""

import os
import platform
import subprocess
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from tests.compare_coverage.acceptance.checker import (
    REPO_ROOT,
    a_run,
    compare_on,
    legacy_side,
    roots,
    rows,
    run_checker,
    table_rows,
    v2_side,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.cli import prepare
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.entries import Entry, Library, entry_file
from tools.compare_coverage.library_probe import installed
from tools.compare_coverage.sides import Limits, SideReport, SideRequest, installed_of

WERKZEUG = "werkzeug.http::parse_list_header"
QUOTE = "urllib.parse::quote"

CHECK = "def check(x: int) -> int:\n    if x > 0:\n        return 1\n    return 0\n"


def git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.mark.legacy
@pytest.mark.timeout(600)
def test_runs_legacy_files_in_place(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-runs-legacy-files-in-place"""
    before = git_status()

    result = run_checker(
        "--legacy", str(legacy_checkout), "--set", "examples", "--budget", "1", timeout=400
    )

    found = rows(result.stdout, result.stderr)
    examples = (legacy_checkout / "examples").resolve()
    programs = {str(file) for file in examples.rglob("*.py") if file.name != "__init__.py"}
    assert len(found) == 22
    assert {row["file"] for row in found} == programs
    for row in found:
        assert row["set"] == "examples"
        assert row["v2"]["file"] == row["legacy"]["file"] == row["file"], row
    assert git_status() == before


class EchoSide:
    """A side that loads the file its request names at once and covers none of its lines."""

    def given(self, limits: Limits) -> Mapping[str, float]:
        return {"budget": limits.budget}

    def run(self, request: SideRequest) -> SideReport:
        module = request.target.split("::")[0]
        if request.library is None:
            return SideReport(file=str(entry_file(module, request.root)), stopped="done")
        library = installed_of(installed(request.library, module))
        assert library is not None and library.root is not None, request.library
        file = entry_file(module, Path(library.root))
        return SideReport(file=str(file), stopped="done", library=library)


@pytest.mark.legacy
# the first legacy test to run builds the checkout, as the conftest says
@pytest.mark.timeout(180)
def test_runs_every_set(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-runs-every-set"""
    run, _ = prepare(["--legacy", str(legacy_checkout)], os.environ)

    code, found, _ = compare_on(run, Sides(v2=EchoSide(), legacy=EchoSide()))

    by_set = Counter(row["set"] for row in found)
    assert set(by_set) == {"v2", "fixtures", "examples", "realworld", "library"}
    assert by_set["realworld"] == 22
    # every entry's file is where its set says, with a def or class of the name, and every
    # scanned file has an entry
    assert [row for row in found if row["status"] not in ("same", "left out")] == []
    assert code == 0


@pytest.mark.legacy
# the first legacy test to run builds the checkout, as the conftest says
@pytest.mark.timeout(180)
def test_names_library_versions(legacy_checkout: Path) -> None:
    """compare-coverage-against-legacy-names-library-versions"""
    result = run_checker(
        "--legacy", str(legacy_checkout), "--target", WERKZEUG, "--target", QUOTE, "--budget", "1"
    )

    by_target = {row["target"]: row for row in rows(result.stdout, result.stderr)}
    werkzeug, quote = by_target[WERKZEUG], by_target[QUOTE]
    assert werkzeug["library"] == "werkzeug==3.1.3"
    assert werkzeug["v2"]["library"] == werkzeug["legacy"]["library"] == "3.1.3"
    # the standard library's version is Python's, which both environments share here
    assert quote["library"] == "python==3.12"
    assert quote["v2"]["library"] == quote["legacy"]["library"] == platform.python_version()
    (line,) = table_rows(result.stderr, WERKZEUG)
    assert line.count("werkzeug 3.1.3") == 2


def library_entry(target: str, seed: dict[str, object], library: Library) -> Entry:
    module, name = target.split("::")
    return Entry(set="realworld", module=module, name=name, seed=seed, library=library)


# fakelib is in the stub's environment alone, and the stub's werkzeug is 0.1, not the pinned
ONLY_LEGACY = library_entry("fakelib.c::check", {"x": 0}, Library("fakelib", "1.0"))
OTHER_VERSION = library_entry(WERKZEUG, {"value": "a, b"}, Library("werkzeug", "3.1.3"))
HEADER = "def parse_list_header(value: str) -> list[str]:\n    return value.split(',')\n"


def test_fails_a_missing_or_mismatched_library(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-fails-a-missing-or-mismatched-library"""
    folder = stub_checkout.install("fakelib", "1.0", {"fakelib/c.py": CHECK})
    stub_checkout.install(
        "werkzeug", "0.1", {"werkzeug/__init__.py": "", "werkzeug/http.py": HEADER}
    )
    entries = [ONLY_LEGACY, OTHER_VERSION]
    run = a_run(entries, roots(stub_checkout.path), limits=Limits(budget=2.0))
    sides = Sides(v2=v2_side(), legacy=legacy_side(stub_checkout.path))

    code, (missing, other), stderr = compare_on(run, sides)

    assert missing["status"] == "v2 failed"
    assert missing["v2"]["failure"] == "the entry pins fakelib 1.0; this side has none"
    assert missing["legacy"]["failure"] is None
    assert missing["legacy"]["library"] == "1.0"
    # the own lines come from the side that has the library
    assert missing["file"] == str(folder / "fakelib" / "c.py")
    assert missing["own_lines"] == [2, 3, 4]
    assert other["status"] == "legacy failed"
    assert other["legacy"]["failure"] == "the entry pins werkzeug 3.1.3; this side has 0.1"
    assert other["v2"]["failure"] is None
    assert other["v2"]["library"] == "3.1.3"
    assert "the entry pins fakelib 1.0; this side has none" in stderr
    assert code == 1


def test_a_library_neither_side_has_fails_both_and_reads_no_file(
    stub_checkout: StubCheckout,
) -> None:
    entry = Entry(
        set="library", module="nolib.m", name="f", seed={}, library=Library("nolib", "2.0")
    )
    sides = Sides(v2=v2_side(), legacy=legacy_side(stub_checkout.path))

    code, (row,), _ = compare_on(a_run([entry], roots(stub_checkout.path)), sides)

    pinned = "the entry pins nolib 2.0; this side has none"
    assert row["status"] == "both failed"
    assert row["v2"]["failure"] == row["legacy"]["failure"] == pinned
    assert (row["file"], row["own_lines"]) == (None, [])
    assert code == 1


class OtherVersionSide(EchoSide):
    """An echoing side whose copy of every library is at 0.1."""

    def run(self, request: SideRequest) -> SideReport:
        report = super().run(request)
        assert report.library is not None
        return replace(report, library=replace(report.library, version="0.1"))


def test_a_library_file_with_no_def_of_the_name_names_each_version_and_the_reason(
    tmp_path: Path,
) -> None:
    entry = library_entry("werkzeug.http::no_such_name", {}, Library("werkzeug", "3.1.3"))
    echo = Sides(v2=EchoSide(), legacy=OtherVersionSide())

    code, (row,), _ = compare_on(a_run([entry], roots(tmp_path)), echo)

    assert row["status"] == "both failed"
    assert row["library"] == "werkzeug==3.1.3"
    assert (row["v2"]["library"], row["legacy"]["library"]) == ("3.1.3", "0.1")
    assert row["v2"]["failure"].endswith("has no top-level def or class named no_such_name")
    # the library explains the other side first
    assert row["legacy"]["failure"] == "the entry pins werkzeug 3.1.3; this side has 0.1"
    assert code == 1


def test_a_library_file_with_no_def_of_the_name_fails_both_pinned_sides(tmp_path: Path) -> None:
    entry = library_entry("werkzeug.http::no_such_name", {}, Library("werkzeug", "3.1.3"))
    echo = Sides(v2=EchoSide(), legacy=EchoSide())

    code, (row,), _ = compare_on(a_run([entry], roots(tmp_path)), echo)

    assert row["status"] == "both failed"
    for side in ("v2", "legacy"):
        assert row[side]["library"] == "3.1.3"
        assert row[side]["failure"].endswith("has no top-level def or class named no_such_name")
    assert code == 1
