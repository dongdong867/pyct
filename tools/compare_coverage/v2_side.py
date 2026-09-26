"""The v2 side: this checkout's ``pyct run``, in a process of its own, read by its summary line.

It runs exactly what a person runs, ``pyct run MODULE::NAME --args SEED`` with the three
limit flags, and reads the summary line ``pyct run`` prints today: the only stdout line with
a ``stopped`` key. That line's ``environment`` must name the checker's own Python and
platform, or the side did not run in this checkout's environment and fails.
"""

import json
import platform
from collections.abc import Mapping
from dataclasses import dataclass

from tools.compare_coverage.process import Command, run_command
from tools.compare_coverage.sides import (
    Limits,
    SideReport,
    SideRequest,
    lines_of,
    optional_count,
    optional_text,
    read_report,
)


@dataclass(frozen=True)
class Stamp:
    """The Python version and platform a run names, as ``pyct run``'s summary line gives them."""

    python: str
    platform: str

    @classmethod
    def here(cls) -> "Stamp":
        return cls(python=platform.python_version(), platform=platform.platform())


@dataclass(frozen=True)
class V2Side:
    """``program`` starts this checkout's pyct; ``stamp`` is the checker's own environment."""

    program: tuple[str, ...]
    environment: Mapping[str, str]
    stamp: Stamp

    def given(self, limits: Limits) -> Mapping[str, float]:
        return {
            "budget": limits.budget,
            "plateau": limits.plateau,
            "solver_timeout": limits.solver_timeout,
        }

    def run(self, request: SideRequest) -> SideReport:
        limits = request.limits
        argv = (
            *self.program,
            *("run", request.target, "--args", json.dumps(request.seed)),
            *("--budget", repr(limits.budget), "--plateau", str(limits.plateau)),
            *("--solver-timeout", repr(limits.solver_timeout)),
        )
        finished = run_command(Command(argv, request.root, self.environment), request.wait)
        return read_report(finished, "stopped", self._report)

    def _report(self, summary: dict[str, object]) -> SideReport:
        covered = summary["covered"]
        if not isinstance(covered, dict) or len(covered) != 1:
            raise ValueError(f"covered must name the one file the run loaded, got {covered!r}")
        ((file, lines),) = covered.items()
        return SideReport(
            file=file,
            covered=lines_of(lines),
            stopped=optional_text(summary["stopped"]),
            inputs=optional_count(summary["inputs"]),
            failure=self._stamp_failure(summary.get("environment")),
        )

    def _stamp_failure(self, environment: object) -> str | None:
        """Why the run did not run here, or ``None`` when it names the checker's own stamp."""
        if not isinstance(environment, dict):
            return "the summary line has no environment"
        theirs = Stamp(
            python=str(environment.get("python")), platform=str(environment.get("platform"))
        )
        if theirs == self.stamp:
            return None
        return (
            f"ran in Python {theirs.python} on {theirs.platform}, "
            f"the checker in Python {self.stamp.python} on {self.stamp.platform}"
        )
