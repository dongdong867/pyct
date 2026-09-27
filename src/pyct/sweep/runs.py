"""One entry's ``pyct run``: its command, a temporary directory of its own, and its row.

Each entry runs as the ``pyct run`` a person would type, with the same flags,
in a process of its own (sweep-runs-each-entry-as-pyct-run), so a crash, an
exit, or a hang costs that entry's row and nothing else.

It starts in a fresh, empty temporary directory that is deleted once its row
is known (sweep-runs-each-entry-in-a-temporary-directory). Sweep calls every
entry with inputs it made up, so a file an entry writes by a relative path
lands there instead of the person's project, and no entry sees another's
files. The directory does not catch a write to any other path or a request
an input sends. ``pyct run`` puts its working directory, the empty one,
first on the path, so the run starts through a boot that puts sweep's own
working directory there too: the entry's module still imports from the file
the listing found. ``PYCT_CACHE_DIR`` names the cache folder sweep would
use, ``.pyct_cache`` in its own working directory unless the variable
already names one, so every entry keeps its substituted code in the one
cache rather than in a temporary directory deleted after it
(interception-code-cached-for-this-user-where-pyct-runs). The run otherwise
gets the environment sweep got.
"""

import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TypeGuard

from pyct.intercept.cache import CACHE_VARIABLE, cache_folder
from pyct.run.process import how
from pyct.sweep.process import Finished, run_command
from pyct.sweep.result import SweepLimits
from pyct.sweep.rows import Row, Status

# what starts pyct, given the folder the entry's module imports from and then pyct's arguments:
# pyct is imported before that folder joins the import path, so nothing in it, a pyct package
# included, can stand in for pyct; pyct's own modules then come through pyct's own path. -P keeps
# the entry's empty working directory off the path until pyct run puts it there
_BOOT = (
    "import runpy, sys; import pyct; sys.path.insert(0, sys.argv.pop(1)); "
    "runpy.run_module('pyct', run_name='__main__', alter_sys=True)"
)

# pyct, started with sweep's own interpreter, so each run has sweep's Python
PYCT: tuple[str, ...] = (sys.executable, "-P", "-c", _BOOT)


def run_entry(row: Row, limits: SweepLimits, *, budget: float, pyct: tuple[str, ...] = PYCT) -> Row:
    """Run a listed entry with its seed, a budget of ``budget`` seconds, and ``limits``' plateau
    and solver timeout.

    The row is ``ran`` when its run exits 0 and prints its summary line, and
    ``failed`` otherwise, keeping the summary line when there was one. A run
    still going ``limits.grace`` seconds past its budget is stopped with
    every process it started.
    """
    here = os.getcwd()
    argv = [*pyct, here, "run", f"{row.module}::{row.name}", "--args", json.dumps(row.seed)]
    argv += ["--budget", repr(budget), "--plateau", str(limits.plateau)]
    argv += ["--solver-timeout", repr(limits.solver_timeout)]
    with tempfile.TemporaryDirectory(prefix="pyct-sweep-") as directory:
        limit = budget + limits.grace
        env = {**os.environ, CACHE_VARIABLE: str(cache_folder())}
        finished = run_command(argv, cwd=Path(directory), env=env, limit=limit)
    return _outcome(row, finished, limits.grace)


def _outcome(row: Row, finished: Finished, grace: float) -> Row:
    """The row a finished run makes."""
    summary = _summary(finished.stdout)
    waited = finished.waited
    if waited is None:
        reason = f"stopped {grace:g} s past its budget"
    elif waited.signal is not None:
        reason = how(waited)
    elif waited.code == 0 and summary is not None:
        return replace(row, status=Status.RAN, run=summary)
    else:
        reason = f"exit {waited.code}: {_last_line(finished.stderr)}"
    return replace(row, status=Status.FAILED, reason=reason, run=summary)


def _summary(stdout: str) -> Mapping[str, object] | None:
    """The last stdout line with the shape of the summary line ``pyct run`` prints last.

    The target's own prints reach the same stdout, and one may carry
    ``stopped`` too, so a line counts only when it has the summary's shape,
    ``SUMMARY_SHAPE``. A line a killed run cut short is no line.
    """
    for line in reversed(stdout.splitlines()):
        try:
            read = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            continue
        if _is_summary(read):
            return read
    return None


def _is_summary(read: object) -> TypeGuard[dict[str, object]]:
    """Whether ``read`` has every key of the summary line, each holding its kind of value."""
    return isinstance(read, dict) and all(
        key in read and fits(read[key]) for key, fits in SUMMARY_SHAPE.items()
    )


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_map(fits: Callable[[object], bool]) -> Callable[[object], bool]:
    """A check for a JSON object whose every value passes ``fits``."""
    return lambda value: isinstance(value, dict) and all(fits(item) for item in value.values())


def _are_lines(value: object) -> bool:
    return isinstance(value, list) and all(_is_count(line) for line in value)


# the summary line ``pyct run`` prints last (``pyct.results.jsonl.render_summary``): each key,
# and a check of the kind of value it holds
SUMMARY_SHAPE: Mapping[str, Callable[[object], bool]] = {
    "stopped": lambda value: isinstance(value, str),
    "inputs": _is_count,
    "solver": _is_map(_is_count),
    "misses": lambda value: isinstance(value, list),
    "covered": _is_map(_are_lines),
    "total": _is_map(_is_count),
    "uncovered": _is_map(_are_lines),
    "environment": lambda value: isinstance(value, dict),
}


def _last_line(stderr: str) -> str:
    """The last line with text that the run wrote to stderr, or nothing."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else ""
