"""Tests for Solver (mock executor)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pyct.core.int import ConcolicInt
from pyct.solver.executor import SolverStatus
from pyct.solver.solver import Solver
from pyct.utils.logger import configure_logging


@pytest.fixture(autouse=True)
def _setup_custom_log_levels():
    """Ensure the custom smtlib2 log level is registered."""
    configure_logging(verbose=0)


class TestFindModel:
    """Solver.find_model delegates to executor and parses results."""

    @patch("pyct.solver.executor.subprocess.run")
    def test_sat_returns_model(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"sat\n((x_VAR 42))\n",
            stderr=b"",
        )
        solver = Solver()
        constraint = MagicMock()
        constraint.get_path_predicates.return_value = []
        model, status, error = solver.find_model(constraint, {"x_VAR": "Int"})
        assert status == SolverStatus.SAT
        assert model == {"x": 42}
        assert error == ""

    @patch("pyct.solver.executor.subprocess.run")
    def test_unsat_returns_none_with_message(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"unsat\n",
            stderr=b"",
        )
        solver = Solver()
        constraint = MagicMock()
        constraint.get_path_predicates.return_value = []
        model, status, error = solver.find_model(constraint, {})
        assert model is None
        assert status == SolverStatus.UNSAT
        assert "unsatisfiable" in error.lower()

    @patch("pyct.solver.executor.subprocess.run")
    def test_unknown_returns_none_with_message(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"unknown\n", stderr=b"")
        solver = Solver()
        constraint = MagicMock()
        constraint.get_path_predicates.return_value = []
        model, status, error = solver.find_model(constraint, {})
        assert model is None
        assert status == SolverStatus.UNKNOWN
        assert "UNKNOWN" in error

    @patch("pyct.solver.executor.subprocess.run")
    def test_error_returns_none_with_message(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b'(error "something")\n',
            stderr=b"",
        )
        solver = Solver()
        constraint = MagicMock()
        constraint.get_path_predicates.return_value = []
        model, status, error = solver.find_model(constraint, {})
        assert model is None
        assert status == SolverStatus.ERROR

    @patch("pyct.solver.executor.subprocess.run")
    def test_parse_failure_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"sat\nbad output\n",
            stderr=b"",
        )
        solver = Solver()
        constraint = MagicMock()
        constraint.get_path_predicates.return_value = []
        model, status, _ = solver.find_model(constraint, {"x_VAR": "Int"})
        assert status == SolverStatus.SAT
        assert model is None  # parse_model raised


class TestValidateExpression:
    """Solver.validate_expression with different safety levels."""

    def test_safety_zero_noop(self, engine):
        solver = Solver(safety=0)
        ci = ConcolicInt(5, "x", engine)
        result = solver.validate_expression(ci, 5)
        assert result is engine

    def test_no_engine_returns_none(self):
        solver = Solver(safety=0)
        result = solver.validate_expression("plain_expr", 5)
        assert result is None

    @patch("pyct.solver.executor.subprocess.run")
    def test_safety_one_sat_returns_engine(self, mock_run, engine):
        mock_run.return_value = MagicMock(stdout=b"sat\n", stderr=b"")
        solver = Solver(safety=1)
        ci = ConcolicInt(5, "x", engine)
        result = solver.validate_expression(ci, 5)
        assert result is engine

    @patch("pyct.solver.executor.subprocess.run")
    def test_safety_one_non_sat_returns_none(self, mock_run, engine):
        mock_run.return_value = MagicMock(stdout=b"unsat\n", stderr=b"")
        solver = Solver(safety=1)
        ci = ConcolicInt(5, "x", engine)
        result = solver.validate_expression(ci, 5)
        assert result is None
