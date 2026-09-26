"""``compare``: one row per entry, then the summary, and the exit code a merge gate reads.

Entries run in list order, one at a time, and within a row the v2 side runs before the
legacy side, never beside it. Sides that run one after the other get the same machine, so a
budget means the same on both. Each row prints as soon as it finishes. A side's trouble is
its row's failure, never an error of the run, so every entry gets its row.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from tools.compare_coverage.accepted import Accepted, mark, passes, rewritten, write_records
from tools.compare_coverage.body import BodyError, read_body
from tools.compare_coverage.entries import Entry, Origin, SetSpec, Unlisted, entry_file
from tools.compare_coverage.output import Facts, row_line, summary_line, table_line, totals_line
from tools.compare_coverage.rows import (
    Reports,
    Row,
    Status,
    compared_row,
    left_out_row,
    unlisted_row,
    unreadable_row,
)
from tools.compare_coverage.sides import Limits, Side, SideRequest

# how long past its budget a side may run before it is stopped
GRACE_SECONDS = 60.0

__all__ = ["GRACE_SECONDS", "Facts", "Run", "Sides", "Streams", "compare"]


@dataclass(frozen=True)
class Run:
    """What one run compares: the entries and where their files live, the limits, the facts.

    ``grace`` is how long past the budget a side runs before it is stopped. ``unlisted`` are
    the files no entry names. ``accepted`` is the file of accepted differences, if given.
    """

    entries: tuple[Entry, ...]
    sets: Mapping[str, SetSpec]
    roots: Mapping[Origin, Path]
    limits: Limits
    facts: Facts
    grace: float = GRACE_SECONDS
    unlisted: tuple[Unlisted, ...] = ()
    accepted: Accepted | None = None


@dataclass(frozen=True)
class Sides:
    v2: Side
    legacy: Side


@dataclass(frozen=True)
class Streams:
    out: TextIO
    err: TextIO


def compare(run: Run, sides: Sides, streams: Streams) -> int:
    """Print every row and the summary, rewrite the accepted file if asked, give the exit code."""
    records = {} if run.accepted is None else run.accepted.records
    rows: list[Row] = []
    for row in _rows(run, sides):
        marked = mark(row, records)
        print(row_line(marked), file=streams.out, flush=True)
        print(table_line(marked), file=streams.err, flush=True)
        rows.append(marked)
    limits = {"v2": sides.v2.given(run.limits), "legacy": sides.legacy.given(run.limits)}
    print(summary_line(rows, limits, run.facts), file=streams.out, flush=True)
    print(totals_line(rows), file=streams.err, flush=True)
    # the file --accept rewrites, or None when this run only reads records or has none
    rewriting = run.accepted if run.accepted is not None and run.accepted.accept else None
    if rewriting is not None:
        write_records(rewriting.path, run.limits, rewritten(rewriting, rows))
    return exit_code(rows, accepting=rewriting is not None)


def exit_code(rows: list[Row], accepting: bool) -> int:
    """1 for a file no entry names; else, unless accepting, 1 for any row that does not pass."""
    if any(row.status is Status.NOT_LISTED for row in rows):
        return 1
    return 0 if accepting or all(passes(row) for row in rows) else 1


def _rows(run: Run, sides: Sides) -> Iterator[Row]:
    for entry in run.entries:
        yield _row(entry, run, sides)
    for unlisted in run.unlisted:
        yield unlisted_row(unlisted)


def _row(entry: Entry, run: Run, sides: Sides) -> Row:
    """The entry's row: left out, unreadable, or compared after both sides ran it."""
    root = run.roots[run.sets[entry.set].origin]
    file = entry_file(entry.module, root)
    if entry.name is None or entry.target is None:
        return left_out_row(entry, file)
    try:
        body = read_body(file, entry.name)
    except BodyError as error:
        return unreadable_row(entry, file, str(error))
    wait = run.limits.budget + run.grace
    request = SideRequest(entry.target, entry.seed, root, run.limits, wait)
    reports = Reports(v2=sides.v2.run(request), legacy=sides.legacy.run(request))
    return compared_row(entry, file, body, reports)
