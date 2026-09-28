"""A row from an entry, its body and the two reports: status first from failures, then lines."""

from dataclasses import replace
from pathlib import Path

import pytest

from tools.compare_coverage.body import Body
from tools.compare_coverage.entries import Entry, Library, Unlisted
from tools.compare_coverage.rows import (
    Files,
    Reports,
    Row,
    SideView,
    Status,
    budget_bound,
    compared_row,
    installed_files,
    left_out_row,
    unlisted_row,
    unreadable_row,
)
from tools.compare_coverage.sides import Installed, SideReport

FILE = Path("/checkout/targets/t.py")
ONE = Files.one(FILE)
ENTRY = Entry(set="v2", module="targets.t", name="f", seed={"x": 0})
# own lines 2, 3 and 5; line 4 is inside the statement on line 3
BODY = Body(own_lines=frozenset({2, 3, 5}), first_line={2: 2, 3: 3, 4: 3, 5: 5})


def report(*lines: int, failure: str | None = None, file: Path = FILE) -> SideReport:
    return SideReport(
        file=str(file), covered=frozenset(lines), stopped="done", inputs=2, failure=failure
    )


def test_both_sides_on_the_same_own_lines_are_same() -> None:
    # line 4 stands for 3, and line 1 is outside the body
    row = compared_row(ENTRY, ONE, BODY, Reports(v2=report(1, 2, 4), legacy=report(2, 3)))

    assert row.status is Status.SAME
    assert row.own_lines == (2, 3, 5)
    assert row.v2 == SideView(
        file=str(FILE), covered=(2, 3), stopped="done", inputs=2, failure=None
    )
    assert (row.only_legacy, row.only_v2) == ((), ())
    assert (row.target, row.seed, row.file) == ("targets.t::f", {"x": 0}, str(FILE))


def test_lines_only_one_side_covered_make_a_difference() -> None:
    row = compared_row(ENTRY, ONE, BODY, Reports(v2=report(2, 5), legacy=report(2, 3)))

    assert row.status is Status.DIFFERS
    assert row.only_legacy == (3,)
    assert row.only_v2 == (5,)


def test_a_failed_side_is_shown_but_not_compared() -> None:
    reports = Reports(v2=report(2, failure="exit 1: boom"), legacy=report(2, 3))

    row = compared_row(ENTRY, ONE, BODY, reports)

    assert row.status is Status.V2_FAILED
    assert row.v2 is not None
    assert row.v2.covered == (2,)
    assert (row.only_legacy, row.only_v2) == ((), ())


def test_each_side_can_fail_alone_or_both_together() -> None:
    failed = report(failure="no summary line")

    legacy = compared_row(ENTRY, ONE, BODY, Reports(v2=report(2), legacy=failed))
    both = compared_row(ENTRY, ONE, BODY, Reports(v2=failed, legacy=failed))

    assert legacy.status is Status.LEGACY_FAILED
    assert both.status is Status.BOTH_FAILED


def test_a_side_that_loaded_another_file_fails_naming_both_and_shows_no_lines() -> None:
    elsewhere = Path("/usr/lib/python/t.py")

    row = compared_row(
        ENTRY, ONE, BODY, Reports(v2=report(2, 3, file=elsewhere), legacy=report(2, 3))
    )

    assert row.status is Status.V2_FAILED
    assert row.v2 is not None
    assert row.v2.failure == f"loaded {elsewhere}, the entry names {FILE}"
    assert row.v2.covered == ()


def test_a_side_with_its_own_failure_keeps_that_failure(tmp_path: Path) -> None:
    reports = Reports(v2=SideReport(failure="exit 2: refused"), legacy=report(2))

    row = compared_row(ENTRY, ONE, BODY, reports)

    assert row.v2 == SideView(
        file=None, covered=(), stopped=None, inputs=None, failure="exit 2: refused"
    )


def test_a_report_that_names_no_file_fails_its_side() -> None:
    nameless = SideReport(stopped="done", inputs=1)

    row = compared_row(ENTRY, ONE, BODY, Reports(v2=nameless, legacy=nameless))

    assert row.status is Status.BOTH_FAILED
    assert row.v2 is not None
    assert row.v2.failure == "the report names no file"


def test_an_unreadable_body_fails_both_sides_with_the_reason() -> None:
    row = unreadable_row(ENTRY, FILE, "no def")

    assert row.status is Status.BOTH_FAILED
    assert row.v2 == row.legacy == SideView(None, (), None, None, "no def")


def test_a_left_out_entry_and_an_unlisted_file_have_rows_of_their_own() -> None:
    left = Entry(set="v2", module="targets.t", left_out="why")

    assert left_out_row(left, FILE).status is Status.LEFT_OUT
    assert left_out_row(left, FILE).left_out == "why"
    unlisted = unlisted_row(Unlisted(set="fixtures", file=FILE))
    assert (unlisted.status, unlisted.set, unlisted.file) == (
        Status.NOT_LISTED,
        "fixtures",
        str(FILE),
    )


WERKZEUG = Library(name="werkzeug", version="3.1.3")
LIBRARY_ENTRY = Entry(set="realworld", module="w.http", name="f", seed={}, library=WERKZEUG)


def in_folder(folder: str, *lines: int, version: str | None = "3.1.3") -> SideReport:
    """A side that loaded ``w/http.py`` under ``folder``, its copy of werkzeug at ``version``."""
    library = Installed(version=version, root=folder if version else None, provides=bool(version))
    return SideReport(
        file=f"{folder}/w/http.py", covered=frozenset(lines), stopped="done", library=library
    )


def copies(tmp_path: Path, v2_text: str, legacy_text: str) -> tuple[str, str]:
    """A v2 and a legacy copy of ``w/http.py``, each under its own folder."""
    folders = (str(tmp_path / "v2"), str(tmp_path / "legacy"))
    for folder, text in zip(folders, (v2_text, legacy_text), strict=True):
        Path(folder, "w").mkdir(parents=True)
        Path(folder, "w", "http.py").write_text(text)
    return folders


def test_each_side_loads_the_module_under_its_own_copy_of_the_library(tmp_path: Path) -> None:
    v2_folder, legacy_folder = copies(tmp_path, "same\n", "same\n")
    reports = Reports(v2=in_folder(v2_folder, 2, 3), legacy=in_folder(legacy_folder, 2, 3))

    files = installed_files("w.http", WERKZEUG, reports)
    row = compared_row(LIBRARY_ENTRY, files, BODY, reports)

    v2_file, legacy_file = Path(v2_folder, "w", "http.py"), Path(legacy_folder, "w", "http.py")
    assert files == Files(body=v2_file, v2=v2_file, legacy=legacy_file)
    assert row.status is Status.SAME
    assert (row.file, row.library) == (str(v2_file), "werkzeug==3.1.3")
    assert row.v2 is not None and row.legacy is not None
    assert (row.v2.library, row.legacy.library) == ("3.1.3", "3.1.3")


def test_a_copy_that_differs_from_the_one_the_lines_come_from_fails_naming_both(
    tmp_path: Path,
) -> None:
    # both match the pin, but legacy's copy is not the same file, so its lines are not these
    v2_folder, legacy_folder = copies(tmp_path, "one\n", "two\n")
    reports = Reports(v2=in_folder(v2_folder, 2, 3), legacy=in_folder(legacy_folder, 2, 3))

    row = compared_row(LIBRARY_ENTRY, installed_files("w.http", WERKZEUG, reports), BODY, reports)

    v2_file, legacy_file = Path(v2_folder, "w", "http.py"), Path(legacy_folder, "w", "http.py")
    assert row.status is Status.LEGACY_FAILED
    assert row.legacy is not None
    assert row.legacy.failure == (
        f"loaded {legacy_file}, which differs from {v2_file}, the file the own lines come from"
    )
    assert row.legacy.covered == ()


def test_a_side_with_another_version_fails_first_and_shows_no_lines() -> None:
    # its own failure and its file do not matter: the library explains them
    other = replace(in_folder("/v2", 2, 3, version="3.0.0"), failure="exit 2: no module")
    reports = Reports(v2=other, legacy=in_folder("/legacy", 2, 3))

    files = installed_files("w.http", WERKZEUG, reports)
    row = compared_row(LIBRARY_ENTRY, files, BODY, reports)

    assert files == Files(body=Path("/legacy/w/http.py"), v2=None, legacy=files.legacy)
    assert row.status is Status.V2_FAILED
    assert row.v2 == SideView(
        file="/v2/w/http.py",
        covered=(),
        stopped="done",
        inputs=None,
        failure="the entry pins werkzeug 3.1.3; this side has 3.0.0",
        library="3.0.0",
    )


def legacy_row(legacy: SideReport) -> Row:
    """The row of an installed entry whose v2 side has the pinned werkzeug."""
    reports = Reports(v2=in_folder("/v2", 2), legacy=legacy)
    return compared_row(LIBRARY_ENTRY, installed_files("w.http", WERKZEUG, reports), BODY, reports)


def test_a_side_without_the_library_fails_naming_none() -> None:
    row = legacy_row(in_folder("/legacy", 2, version=None))

    assert row.legacy is not None
    assert row.legacy.failure == "the entry pins werkzeug 3.1.3; this side has none"


@pytest.mark.parametrize("failure", ["no summary line", "stopped after 90 s", "exit 1: boom"])
def test_a_side_that_said_nothing_of_its_library_keeps_its_own_failure(failure: str) -> None:
    row = legacy_row(SideReport(failure=failure))

    assert row.legacy is not None
    assert (row.legacy.failure, row.legacy.library) == (failure, None)


def test_a_side_that_ran_without_naming_its_library_fails_saying_so() -> None:
    row = legacy_row(SideReport(file="/legacy/w/http.py", covered=frozenset({2}), stopped="done"))

    assert row.legacy is not None
    assert row.legacy.failure == "the side did not say where its werkzeug is"
    assert row.legacy.covered == ()


def test_a_library_neither_side_has_reads_no_file() -> None:
    reports = Reports(v2=SideReport(), legacy=SideReport())

    assert installed_files("w.http", WERKZEUG, reports) == Files(body=None, v2=None, legacy=None)


def test_a_pin_that_does_not_provide_the_module_fails_the_side() -> None:
    # the pinned version sits beside the module, but its record does not hold it
    other = in_folder("/legacy", 2)
    assert other.library is not None
    row = legacy_row(replace(other, library=replace(other.library, provides=False)))

    assert row.legacy is not None
    assert row.legacy.failure == "werkzeug 3.1.3 lists no file for w.http"
    assert row.legacy.covered == ()


def test_the_pinned_version_loaded_from_elsewhere_fails_naming_both_paths(tmp_path: Path) -> None:
    v2_folder, legacy_folder = copies(tmp_path, "same\n", "same\n")
    shadow = replace(in_folder(v2_folder, 2, 3), file=str(tmp_path / "elsewhere" / "w" / "http.py"))
    reports = Reports(v2=shadow, legacy=in_folder(legacy_folder, 2, 3))

    row = compared_row(LIBRARY_ENTRY, installed_files("w.http", WERKZEUG, reports), BODY, reports)

    named = Path(v2_folder, "w", "http.py")
    assert row.status is Status.V2_FAILED
    assert row.v2 is not None
    assert row.v2.failure == f"loaded {shadow.file}, the entry names {named}"
    assert row.v2.covered == ()


def test_a_copy_with_other_line_endings_is_the_same_file(tmp_path: Path) -> None:
    # CRLF lines number the same as LF lines, so the own lines are that copy's lines too
    v2_folder, legacy_folder = copies(tmp_path, "one\ntwo\n", "one\r\ntwo\r\n")
    reports = Reports(v2=in_folder(v2_folder, 2, 3), legacy=in_folder(legacy_folder, 2, 3))

    row = compared_row(LIBRARY_ENTRY, installed_files("w.http", WERKZEUG, reports), BODY, reports)

    assert row.status is Status.SAME


def test_a_row_is_budget_bound_when_a_side_ran_for_at_least_the_budget() -> None:
    def ran(v2: float | None, legacy: float | None) -> Row:
        reports = Reports(
            v2=replace(report(2), seconds=v2), legacy=replace(report(2), seconds=legacy)
        )
        return compared_row(ENTRY, ONE, BODY, reports)

    row = ran(1.0, 5.3)
    assert row.v2 is not None and row.legacy is not None
    assert (row.v2.seconds, row.legacy.seconds) == (1.0, 5.3)
    assert budget_bound(ran(1.0, 5.0), 5.0)
    assert budget_bound(ran(5.3, None), 5.0)
    assert not budget_bound(ran(4.9, None), 5.0)
    assert not budget_bound(unreadable_row(ENTRY, FILE, "no def"), 5.0)
