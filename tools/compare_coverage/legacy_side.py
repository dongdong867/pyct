"""The legacy side: legacy's engine in DIR's own interpreter, through the adapter beside this file.

Legacy and v2 are both packages named ``pyct`` with different dependencies, so they never
share an interpreter; only JSON crosses (decision legacy-oracle-through-one-adapter). Before
any target runs, ``probe`` checks that DIR's interpreter imports legacy's engine.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
)

ADAPTER = Path(__file__).with_name("legacy_adapter.py")

RECIPE = (
    "make one with: git worktree add DIR main && uv sync --project DIR --frozen, "
    "then pass --legacy DIR"
)

# importing legacy's engine takes a second or two; anything slower is not answering
PROBE_SECONDS = 60.0

PROBE = (
    "import importlib, json, platform\n"
    "engine = importlib.import_module('pyct')\n"
    "found = callable(getattr(engine, 'run_concolic', None))\n"
    "print(json.dumps({'python': platform.python_version(), 'engine': found}))\n"
)


class LegacyCheckoutError(Exception):
    """``--legacy`` is missing, or names a folder where legacy's engine cannot be imported."""


def interpreter(checkout: Path) -> Path:
    """The interpreter of the checkout's own environment."""
    return checkout / ".venv" / "bin" / "python"


@dataclass(frozen=True)
class LegacySide:
    """Runs the adapter with the checkout's interpreter, in the entry's root."""

    checkout: Path
    environment: Mapping[str, str]

    def given(self, limits: Limits) -> Mapping[str, float]:
        """Legacy takes whole seconds per solve, so the solver timeout is rounded up."""
        return {
            "budget": limits.budget,
            "plateau": limits.plateau,
            "solver_timeout": math.ceil(limits.solver_timeout),
        }

    def run(self, request: SideRequest) -> SideReport:
        payload = {
            "target": request.target,
            "seed": request.seed,
            "root": str(request.root),
            "limits": self.given(request.limits),
        }
        argv = (str(interpreter(self.checkout)), "-P", str(ADAPTER), json.dumps(payload))
        finished = run_command(Command(argv, request.root, self.environment), request.wait)
        return read_report(finished, "covered", _report)


def _report(line: dict[str, object]) -> SideReport:
    return SideReport(
        file=optional_text(line["file"]),
        covered=lines_of(line["covered"]),
        stopped=optional_text(line["stopped"]),
        inputs=optional_count(line["inputs"]),
        failure=optional_text(line["failure"]),
    )


def probe(checkout: Path | None, environment: Mapping[str, str]) -> str:
    """Legacy's Python version, once DIR's own interpreter has imported legacy's engine."""
    if checkout is None:
        raise LegacyCheckoutError(f"--legacy is required: a checkout of main\n{RECIPE}")
    python = interpreter(checkout)
    if not python.exists():
        raise LegacyCheckoutError(f"--legacy {checkout}: no environment at {python}\n{RECIPE}")
    command = Command((str(python), "-P", "-c", PROBE), checkout, environment)
    finished = run_command(command, PROBE_SECONDS)
    answer = result_line(finished.stdout, "engine") if finished.returncode == 0 else None
    if answer is None:
        said = last_line(finished.stderr)
        raise LegacyCheckoutError(
            f"--legacy {checkout}: legacy's engine cannot be imported: {said}\n{RECIPE}"
        )
    if not answer.get("engine"):
        raise LegacyCheckoutError(
            f"--legacy {checkout}: its pyct has no run_concolic, so it is not a checkout of "
            f"main\n{RECIPE}"
        )
    return str(answer.get("python"))
