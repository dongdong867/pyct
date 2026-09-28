"""A side runs one entry and reports what it covered: the seam between the checker and an engine.

This checkout's ``pyct run`` is one side and legacy's engine, through its adapter, the other.
Each runs as a process of its own and prints one JSON line the checker reads. Both fail a
report the same ways: stopped past its wait, a non-zero exit (the code and the last stderr
line), or no line to read (``no summary line``). A side never raises for a target's trouble;
the trouble becomes the report's failure and the row goes on. For an installed entry, each
side's own interpreter also says which copy of the library it has, through
``library_probe.py``.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from tools.compare_coverage.process import Command, Finished, run_command

LIBRARY_PROBE = Path(__file__).with_name("library_probe.py")

# the probe reads package metadata and prints a line; anything slower is not answering
LIBRARY_SECONDS = 30.0


@dataclass(frozen=True)
class Limits:
    """The limits both sides run under, in ``pyct run``'s terms and with its defaults here."""

    budget: float = 30.0
    plateau: int = 5
    solver_timeout: float = 10.0


@dataclass(frozen=True)
class SideRequest:
    """One entry for one side: what to run, from which root, under which limits, how long.

    ``library`` names the distribution an installed entry's module comes from, ``python``
    for the standard library, so the side can say which version it has.
    """

    target: str
    seed: Mapping[str, object]
    root: Path
    limits: Limits
    wait: float
    library: str | None = None


@dataclass(frozen=True)
class Installed:
    """A library as one side's environment has it: its version and the folder its modules
    sit in, or ``None`` for both when it is not installed, and whether it installed the
    entry's module."""

    version: str | None = None
    root: str | None = None
    provides: bool = False


@dataclass(frozen=True)
class SideReport:
    """What a side said: the file it loaded, its raw lines there, how it stopped, and failure.

    ``library`` is the requested library as the side has it, for an installed entry.
    ``reused`` is true when the report is one kept from an earlier run, not a new run's.
    """

    file: str | None = None
    covered: frozenset[int] = frozenset()
    stopped: str | None = None
    inputs: int | None = None
    failure: str | None = None
    library: Installed | None = None
    reused: bool = False


class Side(Protocol):
    """Runs one entry and reports it. ``given`` is the limits as this side is given them."""

    def given(self, limits: Limits) -> Mapping[str, float]: ...

    def run(self, request: SideRequest) -> SideReport: ...


def read_report(
    finished: Finished,
    key: str,
    parse: Callable[[dict[str, object]], SideReport],
    line_name: str = "summary line",
) -> SideReport:
    """The report in the last stdout line carrying ``key``; how the process ended fails it first.

    A line that cannot be read as a report fails the side, naming what was wrong with it.
    ``line_name`` is what a failure calls the line.
    """
    failure = _process_failure(finished)
    line = result_line(finished.stdout, key)
    if line is None:
        return SideReport(failure=failure or f"no {line_name}")
    try:
        report = parse(line)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return SideReport(failure=failure or f"unreadable {line_name}: {error!r}")
    return report if failure is None else replace(report, failure=failure)


def _process_failure(finished: Finished) -> str | None:
    if finished.stopped_after is not None:
        return f"stopped after {finished.stopped_after:g} s"
    if finished.returncode != 0:
        return f"exit {finished.returncode}: {last_line(finished.stderr)}"
    return None


def with_library(
    report: SideReport, python: str, request: SideRequest, environment: Mapping[str, str]
) -> SideReport:
    """``report`` with the requested library as the side's own interpreter finds it.

    The probe starts as the side does, from the entry's root with the side's environment,
    so it reads the side's own search path. A probe that fails fails the side, after any
    failure the side had already.
    """
    if request.library is None:
        return report
    module = request.target.split("::")[0]
    argv = (python, "-P", str(LIBRARY_PROBE), request.library, module)
    command = Command(argv, request.root, environment)
    finished = run_command(command, LIBRARY_SECONDS)
    probed = read_report(finished, "version", _library_report, "library line from the probe")
    if probed.failure is not None:
        failure = f"cannot read which {request.library} it has: {probed.failure}"
        return replace(report, failure=report.failure or failure)
    return replace(report, library=probed.library)


def _library_report(line: dict[str, object]) -> SideReport:
    return SideReport(library=installed_of(line))


def last_line(text: str) -> str:
    """The last line of ``text`` that says anything, or a note that nothing was said."""
    said = [line.strip() for line in text.splitlines() if line.strip()]
    return said[-1] if said else "nothing on stderr"


def result_line(stdout: str, key: str) -> dict[str, object] | None:
    """The last stdout line that is a JSON object with ``key``. A target may print lines too."""
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and key in value:
            return value
    return None


def lines_of(value: object) -> frozenset[int]:
    """A JSON list of line numbers as a set. Anything else is not a report's lines."""
    if not isinstance(value, list) or not all(type(line) is int for line in value):
        raise ValueError(f"covered lines must be a list of line numbers, got {value!r}")
    return frozenset(value)


def optional_text(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"expected text, got {value!r}")
    return value


def installed_of(value: object) -> Installed | None:
    """A report's library, ``{"version", "root", "provides"}`` or ``null``, as sent."""
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value["provides"], bool):
        raise ValueError(f"library must be an object with version, root and provides: {value!r}")
    return Installed(
        version=optional_text(value["version"]),
        root=optional_text(value["root"]),
        provides=value["provides"],
    )


def optional_count(value: object) -> int | None:
    if value is not None and type(value) is not int:
        raise ValueError(f"expected a count, got {value!r}")
    return value
