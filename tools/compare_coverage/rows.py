"""A row: one entry compared, built from the entry's body and the two sides' reports.

A side's lines in a row are its raw lines cut to the target's own lines, so lines outside
the body never reach a row. A side fails when it failed by its own account or loaded a file
other than the one the entry names. The status comes from failures first and lines second:
a failed side's lines are shown but not compared, so ``only_legacy`` and ``only_v2`` stay
empty unless both sides ran.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tools.compare_coverage.body import Body
from tools.compare_coverage.entries import Entry, Unlisted
from tools.compare_coverage.sides import SideReport


class Status(StrEnum):
    """What a row says about its entry."""

    SAME = "same"
    DIFFERS = "differs"
    V2_FAILED = "v2 failed"
    LEGACY_FAILED = "legacy failed"
    BOTH_FAILED = "both failed"
    NOT_LISTED = "not listed"
    LEFT_OUT = "left out"


@dataclass(frozen=True)
class SideView:
    """One side in a row: the file it loaded, its lines cut to the body, how it stopped."""

    file: str | None
    covered: tuple[int, ...]
    stopped: str | None
    inputs: int | None
    failure: str | None


@dataclass(frozen=True)
class Reports:
    """What each side reported for one entry."""

    v2: SideReport
    legacy: SideReport


@dataclass(frozen=True)
class Row:
    """One entry compared, one file no entry names, or one entry left out.

    ``record`` is ``accepted`` or ``changed`` when an accepted file holds a record for the
    row, and ``change`` then says what changed.
    """

    set: str
    status: Status
    file: str
    target: str | None = None
    seed: Mapping[str, object] | None = None
    own_lines: tuple[int, ...] = ()
    only_legacy: tuple[int, ...] = ()
    only_v2: tuple[int, ...] = ()
    v2: SideView | None = None
    legacy: SideView | None = None
    left_out: str | None = None
    record: str | None = None
    change: str | None = None


def left_out_row(entry: Entry, file: Path) -> Row:
    """An entry that leaves its file out: nothing runs for it."""
    return Row(set=entry.set, status=Status.LEFT_OUT, file=str(file), left_out=entry.left_out)


def unlisted_row(unlisted: Unlisted) -> Row:
    """A file no entry names. It never passes; the fix is an entry."""
    return Row(set=unlisted.set, status=Status.NOT_LISTED, file=str(unlisted.file))


def unreadable_row(entry: Entry, file: Path, reason: str) -> Row:
    """An entry whose file has no body to compare: both sides fail, naming why, and none runs."""
    view = SideView(file=None, covered=(), stopped=None, inputs=None, failure=reason)
    return Row(
        set=entry.set,
        status=Status.BOTH_FAILED,
        file=str(file),
        target=entry.target,
        seed=entry.seed,
        v2=view,
        legacy=view,
    )


def compared_row(entry: Entry, file: Path, body: Body, reports: Reports) -> Row:
    """The row for an entry both sides ran."""
    v2 = _view(reports.v2, file, body)
    legacy = _view(reports.legacy, file, body)
    status = _status(v2, legacy)
    compared = status is Status.DIFFERS
    return Row(
        set=entry.set,
        status=status,
        file=str(file),
        target=entry.target,
        seed=entry.seed,
        own_lines=tuple(sorted(body.own_lines)),
        only_legacy=tuple(sorted(set(legacy.covered) - set(v2.covered))) if compared else (),
        only_v2=tuple(sorted(set(v2.covered) - set(legacy.covered))) if compared else (),
        v2=v2,
        legacy=legacy,
    )


def _view(report: SideReport, file: Path, body: Body) -> SideView:
    """The side as the row shows it. Lines of a file other than the entry's are not its lines."""
    return SideView(
        file=report.file,
        covered=tuple(sorted(body.cut(report.covered))) if _in(report, file) else (),
        stopped=report.stopped,
        inputs=report.inputs,
        failure=report.failure or _file_failure(report, file),
    )


def _in(report: SideReport, file: Path) -> bool:
    return report.file is not None and Path(report.file).resolve() == file.resolve()


def _file_failure(report: SideReport, file: Path) -> str | None:
    """Why the report's lines are not the entry's file's lines, or ``None`` when they are."""
    if report.file is None:
        return "the report names no file"
    return None if _in(report, file) else f"loaded {report.file}, the entry names {file}"


def _status(v2: SideView, legacy: SideView) -> Status:
    if v2.failure is not None and legacy.failure is not None:
        return Status.BOTH_FAILED
    if v2.failure is not None:
        return Status.V2_FAILED
    if legacy.failure is not None:
        return Status.LEGACY_FAILED
    return Status.SAME if v2.covered == legacy.covered else Status.DIFFERS
