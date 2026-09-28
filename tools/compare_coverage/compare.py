"""``compare``: one row per entry, then the summary, and the exit code a merge gate reads.

Up to ``jobs`` rows run at once, each in a thread of its own, and within a row the v2 side
runs before the legacy side, never beside it. With one job, entries run in list order, one at
a time, so the two sides of a row get the same machine and a budget means the same on both.
With more, each side shares the machine with whatever rows run beside it then, so a row that
ends near its budget can end otherwise than it does one at a time. Rows print
in list order whatever order they finish in, each as soon as it and every row before it has
finished. A side's trouble is its row's failure, never an error of the run, so every entry
gets its row. Anything that ends the run early, Ctrl-C among them, stops every side still
running, and no side starts after it.

An entry in an installed library runs from an empty folder of its own, so no file of either
checkout can stand in for the library's. Its file is known only once each side says where its
copy of the library is, so its own lines are read after both sides ran.
"""

import contextlib
import tempfile
from collections.abc import Generator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from tools.compare_coverage.accepted import Accepted, mark, passes, rewritten, write_records
from tools.compare_coverage.body import Body, BodyError, read_body
from tools.compare_coverage.entries import Entry, Library, Origin, SetSpec, Unlisted, entry_file
from tools.compare_coverage.output import Facts, row_line, summary_line, table_line, totals_line
from tools.compare_coverage.process import allow_commands, stop_every_command
from tools.compare_coverage.rows import (
    Files,
    Reports,
    Row,
    Status,
    compared_row,
    installed_files,
    left_out_row,
    unlisted_row,
    unreadable_row,
    without_body,
)
from tools.compare_coverage.sides import Limits, Side, SideRequest

# how long past its budget a side may run before it is stopped
GRACE_SECONDS = 60.0

# the body of an entry whose file no side could name or whose file has no def of the name
NO_BODY = Body(own_lines=frozenset(), first_line={})

__all__ = ["GRACE_SECONDS", "Facts", "Run", "Sides", "Streams", "compare"]


@dataclass(frozen=True)
class Run:
    """What one run compares: the entries and where their files live, the limits, the facts.

    ``grace`` is how long past the budget a side runs before it is stopped. ``unlisted`` are
    the files no entry names. ``accepted`` is the file of accepted differences, if given.
    ``jobs`` is how many rows run at once.
    """

    entries: tuple[Entry, ...]
    sets: Mapping[str, SetSpec]
    roots: Mapping[Origin, Path]
    limits: Limits
    facts: Facts
    grace: float = GRACE_SECONDS
    unlisted: tuple[Unlisted, ...] = ()
    accepted: Accepted | None = None
    jobs: int = 1


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
    # closed however the loop ends, so rows still running stop before the run goes on up
    with contextlib.closing(_rows(run, sides)) as found:
        for row in found:
            marked = mark(row, records, run.roots)
            print(row_line(marked), file=streams.out, flush=True)
            print(table_line(marked), file=streams.err, flush=True)
            rows.append(marked)
    limits = {"v2": sides.v2.given(run.limits), "legacy": sides.legacy.given(run.limits)}
    print(summary_line(rows, limits, run.facts), file=streams.out, flush=True)
    print(totals_line(rows), file=streams.err, flush=True)
    # the file --accept rewrites, or None when this run only reads records or has none
    rewriting = run.accepted if run.accepted is not None and run.accepted.accept else None
    if rewriting is not None:
        write_records(rewriting.path, run.limits, rewritten(rewriting, rows, run.roots))
    return exit_code(rows, accepting=rewriting is not None)


def exit_code(rows: list[Row], accepting: bool) -> int:
    """1 for a file no entry names; else, unless accepting, 1 for any row that does not pass."""
    if any(row.status is Status.NOT_LISTED for row in rows):
        return 1
    return 0 if accepting or all(passes(row) for row in rows) else 1


def _rows(run: Run, sides: Sides) -> Generator[Row]:
    # a run stopped before this one refused new commands until now
    allow_commands()
    if run.jobs == 1:
        for entry in run.entries:
            yield _row(entry, run, sides)
    else:
        yield from _rows_at_once(run, sides)
    for unlisted in run.unlisted:
        yield unlisted_row(unlisted)


def _rows_at_once(run: Run, sides: Sides) -> Generator[Row]:
    """Every entry's row, up to ``run.jobs`` running at once, in list order.

    Whatever ends the wait early stops every side still running and refuses any new one
    before it goes on up, and the pool's threads then end before the run does.
    """
    with ThreadPoolExecutor(max_workers=run.jobs, thread_name_prefix="row") as pool:
        try:
            futures = [pool.submit(_row, entry, run, sides) for entry in run.entries]
            for future in futures:
                yield future.result()
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            stop_every_command()
            raise


def _row(entry: Entry, run: Run, sides: Sides) -> Row:
    """The entry's row: left out, unreadable, or compared after both sides ran it."""
    if entry.library is not None:
        return _installed_row(entry, entry.library, run, sides)
    root = run.roots[run.sets[entry.set].origin]
    file = entry_file(entry.module, root)
    if entry.name is None or entry.target is None:
        return left_out_row(entry, file)
    try:
        body = read_body(file, entry.name)
    except BodyError as error:
        return unreadable_row(entry, file, str(error))
    reports = _reports(SideRequest(entry.target, entry.seed, root, run.limits, _wait(run)), sides)
    return compared_row(entry, Files.one(file), body, reports)


def _installed_row(entry: Entry, library: Library, run: Run, sides: Sides) -> Row:
    """The row of an entry in an installed library, read from the side that has it pinned."""
    assert entry.name is not None and entry.target is not None  # parse_list: none is left out
    with tempfile.TemporaryDirectory() as empty:
        request = SideRequest(
            entry.target, entry.seed, Path(empty), run.limits, _wait(run), library.name
        )
        reports = _reports(request, sides)
    files = installed_files(entry.module, library, reports)
    if files.body is None:
        return compared_row(entry, files, NO_BODY, reports)
    try:
        body = read_body(files.body, entry.name)
    except BodyError as error:
        return compared_row(entry, files, NO_BODY, without_body(reports, str(error)))
    return compared_row(entry, files, body, reports)


def _wait(run: Run) -> float:
    return run.limits.budget + run.grace


def _reports(request: SideRequest, sides: Sides) -> Reports:
    return Reports(v2=sides.v2.run(request), legacy=sides.legacy.run(request))
