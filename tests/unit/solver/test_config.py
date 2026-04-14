"""Tests for SolverConfig."""

from __future__ import annotations

import pytest

from pyct.solver.config import SolverConfig


class TestDefaults:
    """Default values for SolverConfig."""

    def test_default_solver(self):
        cfg = SolverConfig()
        assert cfg.solver == "cvc5"

    def test_default_timeout(self):
        assert SolverConfig().timeout == 10

    def test_default_safety(self):
        assert SolverConfig().safety == 0

    def test_default_store_none(self):
        assert SolverConfig().store is None

    def test_default_statsdir_none(self):
        assert SolverConfig().statsdir is None


class TestGetSolverCommand:
    """get_solver_command builds correct CLI args."""

    def test_cvc5_command(self):
        cfg = SolverConfig(solver="cvc5", timeout=15)
        cmd = cfg.get_solver_command()
        assert cmd[0] == "cvc5"
        assert "--produce-models" in cmd
        assert "--tlimit=15000" in cmd

    def test_unsupported_solver_raises(self):
        cfg = SolverConfig(solver="unknown_solver")
        with pytest.raises(NotImplementedError, match="not supported"):
            cfg.get_solver_command()


class TestProperties:
    """should_store_formulas and should_collect_stats."""

    def test_should_store_formulas_true(self):
        assert SolverConfig(store="/tmp/formulas").should_store_formulas is True

    def test_should_store_formulas_false(self):
        assert SolverConfig().should_store_formulas is False

    def test_should_collect_stats_true(self):
        assert SolverConfig(statsdir="/tmp/stats").should_collect_stats is True

    def test_should_collect_stats_false(self):
        assert SolverConfig().should_collect_stats is False

    def test_frozen(self):
        cfg = SolverConfig()
        with pytest.raises(AttributeError):
            cfg.solver = "z3"
