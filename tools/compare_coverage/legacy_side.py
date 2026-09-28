"""The legacy side: legacy's engine in DIR's own interpreter, through the adapter beside this file.

Legacy and v2 are both packages named ``pyct`` with different dependencies, so they never
share an interpreter; only JSON crosses (decision legacy-oracle-through-one-adapter). Before
any target runs, ``probe`` checks that DIR's interpreter imports legacy's engine.

Legacy's line tracer leaves a ``.pyct-cov.*`` file in the temp folder for each input it runs,
and main is never changed. So every legacy process runs with ``TMPDIR``, ``TEMP`` and ``TMP``
naming a folder of its own inside the checker's temp folder. The folder is removed once the
process exits, fails, is stopped at its deadline or is stopped by Ctrl-C. A checker that is
itself killed leaves its one folder, found by its ``pyct-legacy-`` prefix.

With a cache, the side answers from a result kept by an earlier run when there is one, and
keeps each new answer: one from a process that exited 0 and, for an installed entry, said
which copy of the library it has. A side stopped past its wait, one that exited otherwise, or
one whose probe failed is not an answer of legacy's, so it is not kept.
"""

import contextlib
import json
import math
import platform
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.compare_coverage.cache import Cache
from tools.compare_coverage.process import Command, run_command
from tools.compare_coverage.sides import (
    Limits,
    SideReport,
    SideRequest,
    last_line,
    lines_of,
    optional_count,
    optional_text,
    read_report,
    result_line,
    with_library,
)

ADAPTER = Path(__file__).with_name("legacy_adapter.py")

# the standard library entries pin python, so legacy's environment runs the checker's release
RECIPE = (
    "make one with: git worktree add DIR main && "
    "uv sync --project DIR --frozen --extra realworld --extra library "
    f"--python {platform.python_version()}, then pass --legacy DIR"
)

# importing legacy's engine takes a second or two; anything slower is not answering
PROBE_SECONDS = 60.0

PROBE = (
    "import importlib, json, platform\n"
    "engine = importlib.import_module('pyct')\n"
    "found = callable(getattr(engine, 'run_concolic', None))\n"
    "file = getattr(engine, '__file__', None)\n"
    "print(json.dumps({'python': platform.python_version(), 'engine': found, 'file': file}))\n"
)

# where Python's tempfile, and so legacy's line tracer, looks for the temp folder
TEMP_VARIABLES = ("TMPDIR", "TEMP", "TMP")


class LegacyCheckoutError(Exception):
    """``--legacy`` is missing, or names a folder where legacy's engine cannot be imported."""


def interpreter(checkout: Path) -> Path:
    """The interpreter of the checkout's own environment."""
    return checkout / ".venv" / "bin" / "python"


def installed_distributions(checkout: Path) -> tuple[str, ...]:
    """The ``NAME-VERSION.dist-info`` folders of the checkout's own environment, sorted."""
    found = (checkout / ".venv" / "lib").glob("python*/site-packages/*.dist-info")
    return tuple(sorted(folder.name for folder in found))


@contextlib.contextmanager
def own_temp(environment: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """``environment`` with its temp folder a new one, removed when the block exits or raises."""
    with tempfile.TemporaryDirectory(prefix="pyct-legacy-") as folder:
        yield {**environment, **dict.fromkeys(TEMP_VARIABLES, folder)}


@dataclass(frozen=True)
class LegacySide:
    """Runs the adapter with the checkout's interpreter, in the entry's root.

    ``cache`` keeps its answers between runs, or is ``None`` to run every entry.
    """

    checkout: Path
    environment: Mapping[str, str]
    cache: Cache | None = None

    def given(self, limits: Limits) -> Mapping[str, float]:
        """Legacy takes whole seconds per solve, so the solver timeout is rounded up."""
        return {
            "budget": limits.budget,
            "plateau": limits.plateau,
            "solver_timeout": math.ceil(limits.solver_timeout),
        }

    def run(self, request: SideRequest) -> SideReport:
        if self.cache is None:
            return self._answer(request)[0]
        key = self.cache.key(request, self.given(request.limits))
        kept = self.cache.get(key, request.root)
        if kept is not None:
            return kept
        report, answered = self._answer(request)
        if answered:
            self.cache.put(key, report, request.root)
        return report

    def _answer(self, request: SideRequest) -> tuple[SideReport, bool]:
        """The side's report, and whether it is legacy's answer, as the module docstring says."""
        payload = {
            "target": request.target,
            "seed": request.seed,
            "root": str(request.root),
            "limits": self.given(request.limits),
        }
        python = str(interpreter(self.checkout))
        argv = (python, "-P", str(ADAPTER), json.dumps(payload))
        with own_temp(self.environment) as environment:
            finished = run_command(Command(argv, request.root, environment), request.wait)
            report = with_library(
                read_report(finished, "covered", _report), python, request, environment
            )
        probed = request.library is None or report.library is not None
        return report, finished.returncode == 0 and probed


def _report(line: dict[str, object]) -> SideReport:
    return SideReport(
        file=optional_text(line["file"]),
        covered=lines_of(line["covered"]),
        stopped=optional_text(line["stopped"]),
        inputs=optional_count(line["inputs"]),
        failure=optional_text(line["failure"]),
    )


def probe(
    checkout: Path | None, environment: Mapping[str, str], wait: float = PROBE_SECONDS
) -> str:
    """Legacy's Python version, once DIR's own interpreter has imported DIR's legacy engine.

    The engine must be DIR's own, so the rows come from the commit the summary names.
    """
    if checkout is None:
        raise LegacyCheckoutError(f"--legacy is required: a checkout of main\n{RECIPE}")
    answer = _probe_answer(checkout, environment, wait)
    if not answer.get("engine"):
        raise LegacyCheckoutError(
            f"--legacy {checkout}: its pyct has no run_concolic, so it is not a checkout of "
            f"main\n{RECIPE}"
        )
    own = checkout / "src" / "pyct"
    file = answer.get("file")
    if not isinstance(file, str) or not Path(file).resolve().is_relative_to(own.resolve()):
        raise LegacyCheckoutError(
            f"--legacy {checkout}: its interpreter imports legacy's engine from {file}, "
            f"not {own}\n{RECIPE}"
        )
    return str(answer.get("python"))


def _probe_answer(checkout: Path, environment: Mapping[str, str], wait: float) -> dict[str, object]:
    """What DIR's own interpreter says after importing ``pyct``. Anything else is refused."""
    python = interpreter(checkout)
    if not python.exists():
        raise LegacyCheckoutError(f"--legacy {checkout}: no environment at {python}\n{RECIPE}")
    with own_temp(environment) as own:
        try:
            finished = run_command(Command((str(python), "-P", "-c", PROBE), checkout, own), wait)
        except OSError as error:
            raise LegacyCheckoutError(
                f"--legacy {checkout}: cannot start {python}: {error.strerror}\n{RECIPE}"
            ) from error
    answer = result_line(finished.stdout, "engine") if finished.returncode == 0 else None
    if finished.stopped_after is not None:
        raise LegacyCheckoutError(
            f"--legacy {checkout}: importing legacy's engine did not end in {wait:g} s\n{RECIPE}"
        )
    if answer is None:
        said = last_line(finished.stderr)
        raise LegacyCheckoutError(
            f"--legacy {checkout}: legacy's engine cannot be imported: {said}\n{RECIPE}"
        )
    return answer
