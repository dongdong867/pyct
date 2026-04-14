from __future__ import annotations

import logging
import re
import subprocess
import time
from enum import Enum
from pathlib import Path

from pyct.solver.config import SolverConfig
from pyct.solver.stats import SolverStats

log = logging.getLogger("ct.solver.executor")


class SolverStatus(Enum):
    """Solver execution status."""

    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    ERROR = "error"


class SolverExecutor:
    """Executes SMT solver and manages results."""

    def __init__(self, config: SolverConfig, stats: SolverStats):
        self.config = config
        self.stats = stats
        self.formula_counter = 1
        self._setup_directories()

    def _setup_directories(self) -> None:
        """Create formula storage directories if stats collection is enabled."""
        if self.config.statsdir:
            formula_dir = Path(self.config.statsdir) / "formula"
            formula_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, formula: str) -> tuple[SolverStatus, list[str], float, str]:
        """Execute solver with the given formula.

        Returns:
            ``(status, output_lines, elapsed_time, error_message)``
        """
        status, output_lines, elapsed, error_message = self._run_subprocess(formula)

        self._record_stats(status, elapsed)
        self._store_formula(formula, status)

        return status, output_lines, elapsed, error_message

    def _run_subprocess(self, formula: str) -> tuple[SolverStatus, list[str], float, str]:
        """Spawn the solver process and collect its raw output."""
        start_time = time.time()

        try:
            result = subprocess.run(
                self.config.get_solver_command(),
                input=formula.encode(),
                capture_output=True,
                timeout=self.config.timeout + 5,
            )
        except subprocess.TimeoutExpired:
            log.error("Solver timeout exceeded")
            return (
                SolverStatus.UNKNOWN,
                [],
                time.time() - start_time,
                "Solver timeout exceeded",
            )
        except subprocess.CalledProcessError as e:
            log.error("Solver execution failed: %s", e)
            return (
                SolverStatus.ERROR,
                [],
                time.time() - start_time,
                f"Solver execution failed: {e}",
            )

        elapsed = time.time() - start_time
        stdout = result.stdout.decode()
        stderr = result.stderr.decode()

        if not stdout:
            error_msg = stderr if stderr else "No output from solver"
            return SolverStatus.UNKNOWN, [], elapsed, error_msg

        lines = stdout.splitlines()
        status = self._parse_status(lines[0])
        error_message = self._extract_error_message(status, stderr, lines)

        return status, lines[1:], elapsed, error_message

    def _parse_status(self, status_line: str) -> SolverStatus:
        """Parse solver status from the first line of output."""
        status_lower = status_line.lower()
        if "error" in status_lower:
            log.error("Solver error: %s", status_line)
            return SolverStatus.ERROR
        if status_lower == "sat":
            return SolverStatus.SAT
        if status_lower == "unsat":
            return SolverStatus.UNSAT
        return SolverStatus.UNKNOWN

    def _extract_error_message(
        self, status: SolverStatus, stderr: str, stdout_lines: list[str]
    ) -> str:
        """Build an error/warning message from solver output."""
        if status == SolverStatus.ERROR:
            if stderr:
                return stderr.strip()
            return "\n".join(stdout_lines[:10])
        if stderr:
            return stderr.strip()
        return ""

    def _record_stats(self, status: SolverStatus, elapsed: float) -> None:
        """Update statistics counters for this execution."""
        if status == SolverStatus.SAT:
            self.stats.record_sat(elapsed)
        elif status == SolverStatus.UNSAT:
            self.stats.record_unsat(elapsed)
        else:
            self.stats.record_unknown(elapsed)

    def _store_formula(self, formula: str, status: SolverStatus) -> None:
        """Persist the formula to disk if storage is configured."""
        if not self.config.should_store_formulas and not self.config.should_collect_stats:
            return

        filename = f"{self.formula_counter}_{status.value}.smt2"

        if self.config.store is not None:
            self._write_formula_file(formula, filename, self.config.store)

        if self.config.statsdir:
            stats_path = Path(self.config.statsdir) / "formula"
            self._write_formula_file(formula, filename, str(stats_path))

        self.formula_counter += 1

    def _write_formula_file(self, formula: str, filename: str, directory: str) -> None:
        """Write formula to a file, handling both directory and single-ID modes."""
        if re.compile(r"^\d+$").match(directory):
            if int(directory) == self.formula_counter:
                Path(filename).write_text(formula)
        else:
            filepath = Path(directory) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(formula)
