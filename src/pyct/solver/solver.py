from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from pyct.core import Concolic
from pyct.predicate import Predicate
from pyct.solver.config import SolverConfig
from pyct.solver.executor import SolverExecutor, SolverStatus
from pyct.solver.formula_builder import FormulaBuilder
from pyct.solver.model_parser import ModelParser
from pyct.solver.stats import SolverStats

log = logging.getLogger("ct.solver")


class Solver:
    """SMT solver interface for concolic execution.

    Each instance owns its own config, statistics, and executor — no shared
    class-level state.

    Example::

        solver = Solver(solver="cvc5", timeout=10)
        model, status, error = solver.find_model(constraint, var_to_types)
        if model:
            print(f"SAT: {model}")
    """

    def __init__(
        self,
        solver: str = "cvc5",
        timeout: int = 10,
        safety: int = 0,
        store: Optional[str] = None,
        statsdir: Optional[str] = None,
    ):
        self.config = SolverConfig(
            solver=solver,
            timeout=timeout,
            safety=safety,
            store=store,
            statsdir=statsdir,
        )
        self.stats = SolverStats()
        self.executor = SolverExecutor(self.config, self.stats)
        self._formula_builder = FormulaBuilder()
        self._model_parser = ModelParser()

    def get_stats_dict(self) -> Dict[str, float]:
        """Return solver statistics as a flat dictionary."""
        return self.stats.to_dict()

    # ------------------------------------------------------------------
    # Constraint solving
    # ------------------------------------------------------------------

    def find_model(
        self, constraint: Any, var_to_types: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], SolverStatus, str]:
        """Find a satisfying model for a constraint.

        Returns:
            ``(model, status, error_msg)`` — *model* is a variable-name to
            value mapping when SAT, None otherwise.
        """
        formula = self._formula_builder.build_constraint_formula(
            constraint, var_to_types
        )
        log.smtlib2("Solving constraint: %s", constraint)

        status, output_lines, elapsed, error_output = self.executor.execute(formula)

        model = self._parse_model_result(status, output_lines, formula, var_to_types)
        error_msg = self._build_error_message(status, elapsed, error_output, formula)

        log.smtlib2(
            "SMT-id: %d / Status: %s / Model: %s",
            self.executor.formula_counter,
            status.value,
            model,
        )

        return model, status, error_msg

    def _parse_model_result(
        self,
        status: SolverStatus,
        output_lines: List[str],
        formula: str,
        var_to_types: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Parse a SAT result into a model dict, or return None."""
        if status != SolverStatus.SAT:
            if status == SolverStatus.ERROR:
                log.error("Solver error at SMT-id: %d", self.executor.formula_counter)
                log.error("Formula:\n%s", formula)
            return None

        try:
            return self._model_parser.parse_model(output_lines, var_to_types)
        except Exception as e:
            log.error("Failed to parse model: %s", e)
            return None

    def _build_error_message(
        self,
        status: SolverStatus,
        elapsed: float,
        error_output: str,
        formula: str,
    ) -> str:
        """Build a human-readable error message for non-SAT results."""
        if status == SolverStatus.SAT:
            return ""
        if status == SolverStatus.UNSAT:
            return "Constraint is unsatisfiable (UNSAT)"
        if status == SolverStatus.UNKNOWN:
            msg = (
                f"Solver returned UNKNOWN (timeout or too complex after {elapsed:.2f}s)"
            )
            return f"{msg}: {error_output}" if error_output else msg
        log.error("Solver error at SMT-id: %d", self.executor.formula_counter)
        log.error("Formula:\n%s", formula)
        return f"Solver execution error: {error_output or 'Unknown error'}"

    # ------------------------------------------------------------------
    # Expression validation (called from Concolic._validate_with_solver)
    # ------------------------------------------------------------------

    def validate_expression(self, expr: Any, value: Any) -> Optional[Any]:
        """Check that a symbolic expression matches its concrete *value*.

        At safety level 0 this is a no-op (returns the engine immediately).
        At higher levels it builds a validation formula and asks the solver.

        Returns:
            The engine embedded in *expr*, or None if validation fails.
        """
        engine = Concolic.find_engine_in_expr(expr)
        if engine is None:
            return None

        if self.config.safety <= 0:
            return engine

        return self._run_validation(expr, value, engine)

    def _run_validation(self, expr: Any, value: Any, engine: Any) -> Optional[Any]:
        """Execute the solver to verify expr == value."""
        try:
            expr_formula = Predicate.get_formula_shallow(expr)
            is_float = isinstance(value, float)
            formula = self._formula_builder.build_validation_formula(
                expr_formula, value, is_float
            )

            status, _, _, _ = self.executor.execute(formula)

            if status == SolverStatus.SAT:
                return engine

            log.error("Expression validation failed")
            log.error("Formula: %s", formula)
            log.error("Expected: %s", value)

            if self.config.safety >= 2:
                sys.exit(1)

        except Exception as e:
            log.error("Validation error: %s", e)
            if self.config.safety >= 2:
                sys.exit(1)

        return None
