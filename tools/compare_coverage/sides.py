"""A side runs one entry and reports what it covered: the seam between the checker and an engine.

This checkout's ``pyct run`` is one side and legacy's engine, through its adapter, the other.
Each runs as a process of its own and prints one JSON line the checker reads. Both fail a
report the same ways: stopped past its wait, a non-zero exit (the code and the last stderr
line), or no line to read (``no summary line``). A side never raises for a target's trouble;
the trouble becomes the report's failure and the row goes on.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from tools.compare_coverage.process import Finished

NO_SUMMARY = "no summary line"


@dataclass(frozen=True)
class Limits:
    """The limits both sides run under, in ``pyct run``'s terms and with its defaults here."""

    budget: float = 30.0
    plateau: int = 5
    solver_timeout: float = 10.0


@dataclass(frozen=True)
class SideRequest:
    """One entry for one side: what to run, from which root, under which limits, how long."""

    target: str
    seed: Mapping[str, object]
    root: Path
    limits: Limits
    wait: float


@dataclass(frozen=True)
class SideReport:
    """What a side said: the file it loaded, its raw lines there, how it stopped, and failure."""

    file: str | None = None
    covered: frozenset[int] = frozenset()
    stopped: str | None = None
    inputs: int | None = None
    failure: str | None = None


class Side(Protocol):
    """Runs one entry and reports it. ``given`` is the limits as this side is given them."""

    def given(self, limits: Limits) -> Mapping[str, float]: ...

    def run(self, request: SideRequest) -> SideReport: ...


def read_report(
    finished: Finished, key: str, parse: Callable[[dict[str, object]], SideReport]
) -> SideReport:
    """The report in the last stdout line carrying ``key``; how the process ended fails it first.

    A line that cannot be read as a report fails the side, naming what was wrong with it.
    """
    failure = _process_failure(finished)
    line = result_line(finished.stdout, key)
    if line is None:
        return SideReport(failure=failure or NO_SUMMARY)
    try:
        report = parse(line)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return SideReport(failure=failure or f"unreadable summary line: {error!r}")
    return report if failure is None else replace(report, failure=failure)


def _process_failure(finished: Finished) -> str | None:
    if finished.stopped_after is not None:
        return f"stopped after {finished.stopped_after:g} s"
    if finished.returncode != 0:
        return f"exit {finished.returncode}: {last_line(finished.stderr)}"
    return None


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


def optional_count(value: object) -> int | None:
    if value is not None and type(value) is not int:
        raise ValueError(f"expected a count, got {value!r}")
    return value
