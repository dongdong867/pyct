from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverConfig:
    """
    Configuration for SMT solver.

    Attributes:
        solver: Solver name ("cvc5", "z3", etc.)
        timeout: Timeout in seconds
        safety: Safety level (0-2) for value validation
        store: Directory or ID for storing formulas
        statsdir: Directory for statistics output
    """

    solver: str = "cvc5"
    timeout: int = 10
    safety: int = 0
    store: str | None = None
    statsdir: str | None = None

    def get_solver_command(self) -> list[str]:
        """
        Build solver command based on configuration.

        Returns:
            Command as list of arguments

        Raises:
            NotImplementedError: If solver is not supported
        """
        if self.solver == "cvc5":
            cmd = [
                "cvc5",
                "--produce-models",
                "--lang",
                "smt",
                "--quiet",
                "--strings-exp",
            ]
            # Add timeout
            cmd.append(f"--tlimit={1000 * self.timeout}")
            return cmd

        # Can add other solvers here
        # elif self.solver == "z3":
        #     cmd = ["z3", "-in"]
        #     cmd.append(f"-T:{self.timeout}")
        #     return cmd

        raise NotImplementedError(f"Solver '{self.solver}' is not supported")

    @property
    def should_store_formulas(self) -> bool:
        """Check if formulas should be stored."""
        return self.store is not None

    @property
    def should_collect_stats(self) -> bool:
        """Check if statistics should be collected."""
        return self.statsdir is not None
