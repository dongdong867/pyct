"""Benchmark result data models matching legacy JSON schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoverageResult:
    """Coverage measurement for a single runner execution.

    ``executed_line_numbers`` is the flat sorted union of covered lines
    across all baseline scopes — useful for quick line-count checks but
    loses the file-of-origin for multi-file baselines. Downstream tools
    that need to disambiguate should read ``executed_by_file``, which
    holds per-file sorted lists and is populated only when at least one
    line was covered.
    """

    coverage_percent: float = 0.0
    executed_lines: int = 0
    total_lines: int = 0
    executed_line_numbers: list[int] = field(default_factory=list)
    missing_line_numbers: list[int] = field(default_factory=list)
    executed_by_file: dict[str, list[int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "coverage_percent": self.coverage_percent,
            "executed_lines": self.executed_lines,
            "total_lines": self.total_lines,
            "executed_line_numbers": self.executed_line_numbers,
            "missing_line_numbers": self.missing_line_numbers,
        }
        if self.executed_by_file:
            result["executed_by_file"] = self.executed_by_file
        return result


@dataclass
class AttemptInfo:
    """Metadata for one attempt within a multi-attempt run."""

    run_id: int
    coverage: float
    time_seconds: float
    success: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "coverage": self.coverage,
            "time_seconds": self.time_seconds,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class TokenUsage:
    """LLM token usage for a runner execution."""

    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass
class RunnerResult:
    """Result of a single runner on a single target (best of N attempts)."""

    success: bool = False
    coverage: CoverageResult = field(default_factory=CoverageResult)
    time_seconds: float = 0.0
    error: str | None = None
    iterations: int | None = None
    test_cases_generated: int | None = None
    attempts: list[AttemptInfo] = field(default_factory=list)
    captured_output: str = ""
    token_usage: TokenUsage | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "coverage": self.coverage.to_dict(),
            "time_seconds": self.time_seconds,
            "error": self.error,
            "iterations": self.iterations,
            "test_cases_generated": self.test_cases_generated,
            "attempts": [a.to_dict() for a in self.attempts],
            "captured_output": self.captured_output,
        }
        if self.token_usage is not None:
            result["token_usage"] = self.token_usage.to_dict()
        return result


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for a benchmark run."""

    timeout: float = 60.0
    single_timeout: float = 15.0
    max_iterations: int = 50
    num_attempts: int = 3
    verbose: int = 0
    output_dir: str = "benchmark/results"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout": self.timeout,
            "single_timeout": self.single_timeout,
            "max_iterations": self.max_iterations,
            "num_attempts": self.num_attempts,
            "verbose": self.verbose,
            "output_dir": self.output_dir,
        }
