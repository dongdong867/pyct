"""What the compare tool's acceptance tests share: spawn the checker, read its stdout.

The checker runs as a person runs it, ``python -m tools.compare_coverage`` from the
repository root, with ``PYTHONPATH`` removed. coverage.py's startup variables stay, so a
measured test run measures the checker too; the checker keeps them out of each side.
"""

import io
import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from subprocess import PIPE
from typing import Any

from tools.compare_coverage.compare import Facts, Run, Sides, Streams, compare
from tools.compare_coverage.entries import LIST_FILE, Entry, Origin, load_list
from tools.compare_coverage.legacy_side import LegacySide
from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits
from tools.compare_coverage.v2_side import Stamp, V2Side

REPO_ROOT = Path(__file__).resolve().parents[3]

ONE_CHECK = "targets.flip.one_check::classify"
ONE_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
# line 5 is unreachable: x < 5 always holds x < 10, so no engine can cover it
IMPLIED_CHECK = "targets.flip.implied_check::narrow"
TWO_ARGS = "targets.flip.two_args::pick"


def run_checker(
    *argv: str, path: str | None = None, timeout: float = 55
) -> subprocess.CompletedProcess[str]:
    """Spawn the checker with ``argv``. ``path`` replaces its ``PATH``.

    Each side leads a session of its own, so killing a checker past ``timeout`` would leave
    its running side behind. It gets Ctrl-C instead, which stops the side's whole group, and
    is killed only if it has not ended ten seconds later. The timeout then fails the test.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if path is not None:
        env["PATH"] = path
    argv = (sys.executable, "-m", "tools.compare_coverage", *argv)
    with subprocess.Popen(
        argv, cwd=REPO_ROOT, env=env, stdout=PIPE, stderr=PIPE, text=True
    ) as checker:
        try:
            stdout, stderr = checker.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            checker.send_signal(signal.SIGINT)
            try:
                checker.communicate(timeout=10)
            finally:
                checker.kill()
            raise
    return subprocess.CompletedProcess(argv, checker.returncode, stdout, stderr)


def rows(stdout: str) -> list[dict[str, Any]]:
    """Every row line; the summary line that closes stdout is left out, and must be there."""
    lines = [json.loads(line) for line in stdout.splitlines()]
    assert lines and "statuses" in lines[-1], stdout
    return lines[:-1]


def one_row(stdout: str) -> dict[str, Any]:
    found = rows(stdout)
    assert len(found) == 1, stdout
    return found[0]


def summary(stdout: str) -> dict[str, Any]:
    lines = stdout.splitlines()
    assert lines, stdout
    return json.loads(lines[-1])


def table_rows(stderr: str, target: str) -> list[str]:
    """The table lines on stderr that name ``target``."""
    return [line for line in stderr.splitlines() if target in line]


def write_records(file: Path, *records: Mapping[str, Any]) -> None:
    file.write_text("".join(json.dumps(record) + "\n" for record in records))


def read_records(file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in file.read_text().splitlines()]


def v2_side(program: tuple[str, ...] = (sys.executable, "-P", "-m", "pyct")) -> V2Side:
    """The real v2 side, as the checker builds it."""
    return V2Side(program=program, environment=side_environment(os.environ), stamp=Stamp.here())


def legacy_side(checkout: Path) -> LegacySide:
    return LegacySide(checkout=checkout, environment=side_environment(os.environ))


def a_run(entries: Sequence[Entry], roots: Mapping[Origin, Path], **options: object) -> Run:
    """A run of ``entries`` in the committed sets, with a 5 s budget and a one-second grace."""
    facts = Facts(commits={}, python={}, cvc5=None, platform="test")
    fields: dict[str, Any] = {
        "sets": load_list(LIST_FILE).sets,
        "limits": Limits(budget=5.0),
        "grace": 1.0,
        **options,
    }
    return Run(entries=tuple(entries), roots=roots, facts=facts, **fields)


def compare_on(run: Run, sides: Sides) -> tuple[int, list[dict[str, Any]], str]:
    """Run ``compare`` and give its exit code, its rows and its stderr."""
    out, err = io.StringIO(), io.StringIO()
    code = compare(run, sides, Streams(out=out, err=err))
    return code, rows(out.getvalue()), err.getvalue()
