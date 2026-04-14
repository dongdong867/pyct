"""Tests for SolverExecutor (mock subprocess.run)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from pyct.solver.config import SolverConfig
from pyct.solver.executor import SolverExecutor, SolverStatus
from pyct.solver.stats import SolverStats


def _make_executor(**kwargs):
    """Create a SolverExecutor with the given config overrides."""
    config = SolverConfig(**kwargs)
    stats = SolverStats()
    return SolverExecutor(config, stats), stats


class TestStatusParsing:
    """SolverExecutor._parse_status maps first-line text to SolverStatus."""

    def test_sat(self):
        executor, _ = _make_executor()
        assert executor._parse_status("sat") == SolverStatus.SAT

    def test_unsat(self):
        executor, _ = _make_executor()
        assert executor._parse_status("unsat") == SolverStatus.UNSAT

    def test_unknown(self):
        executor, _ = _make_executor()
        assert executor._parse_status("unknown") == SolverStatus.UNKNOWN

    def test_error_line(self):
        executor, _ = _make_executor()
        assert executor._parse_status("(error something)") == SolverStatus.ERROR


class TestExecution:
    """SolverExecutor.execute with mocked subprocess."""

    @patch("pyct.solver.executor.subprocess.run")
    def test_sat_returns_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"sat\n((x_VAR 42))\n",
            stderr=b"",
        )
        executor, stats = _make_executor()
        status, lines, elapsed, error = executor.execute("(check-sat)")
        assert status == SolverStatus.SAT
        assert lines == ["((x_VAR 42))"]
        assert stats.sat_number == 1

    @patch("pyct.solver.executor.subprocess.run")
    def test_unsat_empty_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"unsat\n",
            stderr=b"",
        )
        executor, stats = _make_executor()
        status, lines, _, _ = executor.execute("(check-sat)")
        assert status == SolverStatus.UNSAT
        assert lines == []
        assert stats.unsat_number == 1

    @patch("pyct.solver.executor.subprocess.run")
    def test_timeout_returns_unknown(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="cvc5", timeout=10)
        executor, stats = _make_executor()
        status, lines, _, error = executor.execute("(check-sat)")
        assert status == SolverStatus.UNKNOWN
        assert "timeout" in error.lower()
        assert stats.otherwise_number == 1

    @patch("pyct.solver.executor.subprocess.run")
    def test_no_stdout_returns_unknown(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"", stderr=b"")
        executor, _ = _make_executor()
        status, _, _, _ = executor.execute("(check-sat)")
        assert status == SolverStatus.UNKNOWN


class TestFormulaStorage:
    """Formula storage to disk when configured."""

    @patch("pyct.solver.executor.subprocess.run")
    def test_store_configured_writes_file(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout=b"sat\n", stderr=b"")
        executor, _ = _make_executor(store=str(tmp_path))
        executor.execute("(check-sat)")
        files = list(tmp_path.glob("*.smt2"))
        assert len(files) == 1

    @patch("pyct.solver.executor.subprocess.run")
    def test_statsdir_writes_to_formula_dir(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout=b"sat\n", stderr=b"")
        executor, _ = _make_executor(statsdir=str(tmp_path))
        executor.execute("(check-sat)")
        formula_dir = tmp_path / "formula"
        files = list(formula_dir.glob("*.smt2"))
        assert len(files) == 1

    @patch("pyct.solver.executor.subprocess.run")
    def test_counter_increments(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout=b"sat\n", stderr=b"")
        executor, _ = _make_executor(store=str(tmp_path))
        executor.execute("(check-sat)")
        executor.execute("(check-sat)")
        files = list(tmp_path.glob("*.smt2"))
        assert len(files) == 2
