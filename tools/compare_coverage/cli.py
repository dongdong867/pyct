"""The command line: ``python -m tools.compare_coverage --legacy DIR [flags]``.

Before any target runs, the checks go in this order, each leaving stdout empty: the flags
and the files they name (exit 2), the legacy checkout (exit 2), then cvc5 (exit 1), as
``pyct run`` checks its command line before the machine. The limit flags take the names and
the rules ``pyct run`` gives them. Ctrl-C stops the running side and exits 130.
"""

import argparse
import math
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from tools.compare_coverage.accepted import Accepted, RecordsError, key_of, read_records
from tools.compare_coverage.compare import Facts, Run, Sides, Streams, compare
from tools.compare_coverage.entries import (
    LIST_FILE,
    ListError,
    Origin,
    SelectionError,
    TargetList,
    load_list,
    unlisted_files,
)
from tools.compare_coverage.environment import (
    SolverMissingError,
    commit,
    cvc5_version,
    locate_cvc5,
)
from tools.compare_coverage.legacy_side import LegacyCheckoutError, LegacySide, probe
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits
from tools.compare_coverage.v2_side import Stamp, V2Side

USAGE = (
    "python -m tools.compare_coverage --legacy DIR [--set NAME]... [--target MODULE::NAME]..."
    " [--budget SECONDS] [--plateau N] [--solver-timeout SECONDS] [--accepted FILE [--accept]]"
)

# this checkout: its targets are the v2 set's, and its pyct is the v2 side
REPO_ROOT = Path(__file__).resolve().parents[2]


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


@dataclass(frozen=True)
class Flags:
    """The command line as given, before any check."""

    legacy: Path | None
    sets: tuple[str, ...]
    targets: tuple[str, ...]
    limits: Limits
    accepted: Path | None
    accept: bool


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker and return its exit code: 0 or 1 as the rows decide, 2 for usage."""
    try:
        run, sides = prepare(sys.argv[1:] if argv is None else argv, os.environ)
    except (UsageError, SelectionError, ListError, RecordsError, LegacyCheckoutError) as error:
        print(error, file=sys.stderr)
        return 2
    except SolverMissingError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        return compare(run, sides, Streams(out=sys.stdout, err=sys.stderr))
    except KeyboardInterrupt:
        return 130


def prepare(argv: Sequence[str], environ: Mapping[str, str]) -> tuple[Run, Sides]:
    """Every check before the first target, in the order the module docstring gives."""
    flags = parse_flags(argv)
    target_list = load_list(LIST_FILE)
    entries = target_list.select(flags.sets, flags.targets)
    accepted = _accepted(flags, target_list)
    environment = side_environment(environ)
    legacy_python = probe(flags.legacy, environment)
    cvc5 = locate_cvc5(environ)
    assert flags.legacy is not None  # probe refuses a missing checkout
    roots = {Origin.V2: REPO_ROOT, Origin.LEGACY: flags.legacy}
    facts = Facts(
        commits={"v2": commit(REPO_ROOT), "legacy": commit(flags.legacy)},
        python={"v2": platform.python_version(), "legacy": legacy_python},
        cvc5=cvc5_version(cvc5),
        platform=platform.platform(),
    )
    scanned = target_list.scanned(flags.sets, flags.targets)
    run = Run(
        entries=entries,
        sets=target_list.sets,
        roots=roots,
        limits=flags.limits,
        facts=facts,
        unlisted=unlisted_files(target_list, scanned, roots),
        accepted=accepted,
    )
    return run, _sides(flags.legacy, environment)


def _sides(legacy: Path, environment: Mapping[str, str]) -> Sides:
    v2 = V2Side(
        program=(sys.executable, "-P", "-m", "pyct"), environment=environment, stamp=Stamp.here()
    )
    return Sides(v2=v2, legacy=LegacySide(checkout=legacy, environment=environment))


def _accepted(flags: Flags, target_list: TargetList) -> Accepted | None:
    """The accepted file and its records, or ``None`` when ``--accepted`` is not given."""
    if flags.accepted is None:
        if flags.accept:
            raise UsageError(f"--accept needs --accepted FILE, the file it writes\nusage: {USAGE}")
        return None
    listed = frozenset(
        key_of(entry.target, entry.seed) for entry in target_list.entries if entry.target
    )
    records = read_records(flags.accepted, flags.accept)
    return Accepted(path=flags.accepted, records=records, accept=flags.accept, listed=listed)


def parse_flags(argv: Sequence[str]) -> Flags:
    """The flags, with each limit checked as ``pyct run`` checks it."""
    parser = _Parser(prog="python -m tools.compare_coverage", usage=USAGE)
    parser.add_argument("--legacy", type=Path, metavar="DIR")
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="NAME")
    parser.add_argument("--target", dest="targets", action="append", default=[])
    parser.add_argument("--budget", default="30", metavar="SECONDS")
    parser.add_argument("--plateau", default="5", metavar="N")
    parser.add_argument("--solver-timeout", default="10", metavar="SECONDS")
    parser.add_argument("--accepted", type=Path, metavar="FILE")
    parser.add_argument("--accept", action="store_true")
    given = parser.parse_args(argv)
    limits = Limits(
        budget=_seconds(given.budget, "--budget"),
        plateau=_whole(given.plateau, "--plateau"),
        solver_timeout=_seconds(given.solver_timeout, "--solver-timeout"),
    )
    return Flags(
        legacy=given.legacy,
        sets=tuple(given.sets),
        targets=tuple(given.targets),
        limits=limits,
        accepted=given.accepted,
        accept=given.accept,
    )


def _seconds(text: str, flag: str) -> float:
    """A finite number of seconds above zero, as ``pyct run`` takes its budget."""
    try:
        seconds = float(text)
    except ValueError:
        raise UsageError(f"{flag} must be a number of seconds, got {text!r}") from None
    if not (math.isfinite(seconds) and seconds > 0):
        raise UsageError(f"{flag} must be a finite number of seconds above zero, got {text!r}")
    return seconds


def _whole(text: str, flag: str) -> int:
    """A whole number above zero, as ``int()`` reads one and ``pyct run`` takes its plateau."""
    refusal = f"{flag} must be a whole number above zero, got {text!r}"
    try:
        number = int(text)
    except ValueError:
        raise UsageError(refusal) from None
    if number <= 0:
        raise UsageError(refusal)
    return number


class _Parser(argparse.ArgumentParser):
    """An argparse parser that raises a usage error instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{message}\nusage: {USAGE}")
