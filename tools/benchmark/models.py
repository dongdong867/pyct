"""Benchmark result data models matching legacy JSON schema."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pyct.engine.types import Outcome


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


def _exception_type(error: str | None) -> str:
    """Extract the leading exception class name from an error string.

    Records store errors as ``"AssertionError: msg"`` or, for SystemExit,
    ``"SystemExit(0)"`` — both lead with the class name. Returns
    ``"Unknown"`` when the string is empty or has no leading identifier.
    """
    if not error:
        return "Unknown"
    match = re.match(r"[A-Za-z_]\w*", error)
    return match.group(0) if match else "Unknown"


@dataclass(frozen=True)
class OutcomeCounts:
    """Execution-outcome tally derived from a runner's input records.

    Answers the reviewer's per-execution metrics directly: ``clean_exit``
    (the target returned normally), ``error_exit`` (it raised), and
    ``timeout``. ``by_exception`` breaks the error exits down by exception
    type — ``AssertionError`` appears as its own key, so the
    fault-triggering count needs no post-processing. Purely a projection
    of ``input_records``; it holds no state the records don't.
    """

    total: int = 0
    clean_exit: int = 0
    error_exit: int = 0
    timeout: int = 0
    by_exception: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> OutcomeCounts:
        clean = errors = timeouts = 0
        by_exception: dict[str, int] = {}
        for record in records:
            outcome = record.get("outcome")
            if outcome == Outcome.TIMEOUT:
                timeouts += 1
            elif outcome == Outcome.TARGET_ERROR:
                errors += 1
                exc = _exception_type(record.get("error"))
                by_exception[exc] = by_exception.get(exc, 0) + 1
            else:
                clean += 1
        return cls(
            total=len(records),
            clean_exit=clean,
            error_exit=errors,
            timeout=timeouts,
            by_exception=by_exception,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "clean_exit": self.clean_exit,
            "error_exit": self.error_exit,
            "timeout": self.timeout,
            "by_exception": dict(self.by_exception),
        }


@dataclass
class RunnerResult:
    """Result of a single runner on a single target (best of N attempts).

    The primary reported coverage comes from ``coverage`` — a
    coverage.py-measured rerun of every discovered input. When an
    engine-backed runner (``pure_concolic``, ``concolic_llm``) ran with
    a ``CoverageScope``, the engine's in-loop tracer also produces a
    wide-scope view that can be cross-referenced with the rerun
    number. Those optional fields (``engine_coverage_percent``,
    ``engine_executed_lines``, ``engine_total_lines``) provide the
    dual-reporting signal used for validity claims — if the two
    channels agree, the measurement is well-calibrated; divergence
    highlights tracer or rerun issues worth investigating.
    """

    success: bool = False
    coverage: CoverageResult = field(default_factory=CoverageResult)
    time_seconds: float = 0.0
    error: str | None = None
    iterations: int | None = None
    test_cases_generated: int | None = None
    attempts: list[AttemptInfo] = field(default_factory=list)
    captured_output: str = ""
    token_usage: TokenUsage | None = None
    engine_coverage_percent: float | None = None
    engine_executed_lines: int | None = None
    engine_total_lines: int | None = None
    input_records: list[dict[str, Any]] = field(default_factory=list)
    gen_unsat: int = 0
    gen_unknown: int = 0
    gen_parse_failed: int = 0
    harness_error: int = 0

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
            "input_records": self.input_records,
            "outcome_counts": OutcomeCounts.from_records(self.input_records).to_dict(),
            "gen_unsat": self.gen_unsat,
            "gen_unknown": self.gen_unknown,
            "gen_parse_failed": self.gen_parse_failed,
            "harness_error": self.harness_error,
        }
        if self.token_usage is not None:
            result["token_usage"] = self.token_usage.to_dict()
        if self.engine_coverage_percent is not None:
            result["engine_coverage_percent"] = self.engine_coverage_percent
            result["engine_executed_lines"] = self.engine_executed_lines
            result["engine_total_lines"] = self.engine_total_lines
        return result


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for a benchmark run.

    Attributes:
        coverage_scope: ``"wide"`` (default) tells the concolic engine
            to track coverage across every ``.py`` file under the
            target's ``source_path`` directory — matches how the
            benchmark's own coverage measurement spans the whole
            package, so the engine keeps exploring past thin-wrapper
            targets into deeper library code. Standard-suite targets
            without a ``source_path`` degrade to single-file scope
            automatically. Set to ``"narrow"`` to force classical
            concolic behavior (useful for scope-sensitivity
            ablations against the wide default).
    """

    timeout: float = 60.0
    single_timeout: float = 15.0
    max_iterations: int = 50
    num_attempts: int = 3
    verbose: int = 0
    output_dir: str = "benchmark/results"
    coverage_scope: Literal["narrow", "wide"] = "wide"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout": self.timeout,
            "single_timeout": self.single_timeout,
            "max_iterations": self.max_iterations,
            "num_attempts": self.num_attempts,
            "verbose": self.verbose,
            "output_dir": self.output_dir,
            "coverage_scope": self.coverage_scope,
        }
