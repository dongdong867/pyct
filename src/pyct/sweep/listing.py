"""Sweep's side of the lister: start it, read its facts with a limit, and start it again after
a module ends it or stalls it.

The lister runs in a session of its own, so its process group holds every
process a module's import started, and the whole group is killed once sweep
is done with it, as the compare tool learned. Its facts come over a pipe,
read with a limit: when no fact comes for ``GRACE`` seconds, the module it
was importing gets a failed row and a new lister starts after it. Reading
also watches for the lister's end, so a process a module left holding the
pipe cannot keep sweep waiting.
"""

import contextlib
import json
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass

from pyct.run.process import how
from pyct.sweep.process import stop_group, waited_of
from pyct.sweep.rows import Row, Status

# the lister, started with sweep's own interpreter; -P keeps a folder named pyct in the working
# directory from standing in for pyct, and the lister puts that directory on the path itself
LISTER: tuple[str, ...] = (sys.executable, "-P", "-m", "pyct.sweep.lister")

# how long the lister may go with no fact: the limit on one module's import
GRACE = 60.0

# how often a wait for a fact looks at whether the lister has ended
POLL = 0.05

# the most one read of the pipe takes
CHUNK = 65536


class PackageImportError(Exception):
    """The package itself did not import. The message says so, and how its import ended."""


@dataclass(frozen=True)
class Heard:
    """What one lister said: its rows, and the module it stopped on and how, unless it finished."""

    rows: list[Row]
    stuck: tuple[str, str] | None


def list_package(
    package: str, *, grace: float = GRACE, lister: tuple[str, ...] = LISTER
) -> tuple[Row, ...]:
    """Every row of the package, one per module and entry name, in order.

    An entry several modules export is one row. Raises ``PackageImportError``
    when the package itself does not import, since then nothing is swept. A
    Ctrl-C, the ``Stopped`` a SIGTERM raises in the command's process (see
    ``pyct.run.launch``), or a SIGHUP under
    ``pyct.sweep.process.hangup_stops_children`` stops the lister on its way
    out.
    """
    kept: dict[tuple[str, str], Row] = {}
    after: str | None = None
    while True:
        heard = _listen(package, after, grace, lister)
        for row in heard.rows:
            kept.setdefault(row.order, row)
        if heard.stuck is None:
            return tuple(sorted(kept.values(), key=lambda row: row.order))
        module, ended = heard.stuck
        if module == package:
            raise PackageImportError(_failed(module, ended).reason)
        kept.setdefault((module, ""), _failed(module, ended))
        after = module


def _listen(package: str, after: str | None, grace: float, lister: tuple[str, ...]) -> Heard:
    """Start one lister, hear it out, and stop its whole process group."""
    argv = [*lister, package, *(() if after is None else ("--after", after))]
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return _heard(_Lines(process), package, grace)
    finally:
        _stop(process)


def _heard(lines: "_Lines", package: str, grace: float) -> Heard:
    """The rows the facts make, until ``done``, or until the lister ends or stalls on a module."""
    rows: list[Row] = []
    importing = package
    while (line := lines.next(grace)) is not None:
        fact = json.loads(line)
        if "done" in fact:
            return Heard(rows, None)
        importing = fact.get("importing", importing)
        if fact.get("failed") == package:
            raise PackageImportError(_failed(package, fact["reason"]).reason)
        rows.extend(_rows_of(fact))
    return Heard(rows, (importing, lines.ending(grace)))


def _rows_of(fact: dict[str, object]) -> list[Row]:
    """The row a fact makes: a module whose import or reading raised, or an entry.
    ``importing`` makes none. A fact carries Python's words; the row's are written here."""
    if "failed" in fact:
        return [_failed(str(fact["failed"]), str(fact["reason"]))]
    if "unread" in fact:
        module, name = str(fact["unread"]), fact["name"]
        read = module if name is None else f"{module}::{name}"
        return [Row(module, None, Status.FAILED, reason=f"cannot read {read}: {fact['reason']}")]
    entry = fact.get("entry")
    if not isinstance(entry, dict):
        return []
    if entry["skip"] is None:
        return [Row(entry["module"], entry["name"], Status.LISTED, seed=entry["seed"])]
    return [Row(entry["module"], entry["name"], Status.SKIPPED, reason=entry["skip"])]


def _failed(module: str, ended: str) -> Row:
    return Row(module, None, Status.FAILED, reason=f"cannot import {module}: {ended}")


class _Lines:
    """The lister's facts, line by line, each waited for no longer than a limit."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        self.process = process
        self.fd = process.stdout.fileno()
        self.buffer = b""
        self.closed = False

    def next(self, limit: float) -> str | None:
        """The next whole line, or None once the lister has ended or ``limit`` seconds passed.

        A line cut short by the lister's end is no line.
        """
        deadline = time.monotonic() + limit
        while b"\n" not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or self._ended():
                return None
            self._wait(min(POLL, left))
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line.decode("utf-8")

    def ending(self, grace: float) -> str:
        """How the lister ended, in ``pyct run``'s words, or that it did not end in time."""
        code = self.process.poll()
        if code is None:
            return f"did not finish in {grace:g} s"
        return how(waited_of(code))

    def _ended(self) -> bool:
        """The lister has exited and nothing it wrote is left to read."""
        if self.process.poll() is None:
            return False
        return self.closed or not select.select([self.fd], [], [], 0)[0]

    def _wait(self, seconds: float) -> None:
        """Read what the lister writes within ``seconds``, or wait for its end once the pipe
        has closed."""
        if self.closed:
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=seconds)
            return
        if select.select([self.fd], [], [], seconds)[0]:
            chunk = os.read(self.fd, CHUNK)
            self.buffer += chunk
            self.closed = not chunk


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Kill the lister's whole process group, reap the lister, and close its pipe."""
    stop_group(process)
    if process.stdout is not None:
        process.stdout.close()
