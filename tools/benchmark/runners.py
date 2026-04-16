"""Benchmark runners — one function per execution mode.

Each runner takes a target + config and returns a RunnerResult.
Seed generation is external (done by the suite orchestrator) so
llm_only and concolic_llm receive pre-generated seeds.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from coverage import Coverage

from tools.benchmark.models import (
    BenchmarkConfig,
    CoverageResult,
    RunnerResult,
    TokenUsage,
)
from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.runners")

# ── Runner name constants ──────────────────────────────────────────

PURE_CONCOLIC = "pure_concolic"
CONCOLIC_LLM = "concolic_llm"
LLM_ONLY = "llm_only"
CROSSHAIR = "crosshair"

ALL_RUNNERS = [PURE_CONCOLIC, CONCOLIC_LLM, LLM_ONLY, CROSSHAIR]


# ── Public API ─────────────────────────────────────────────────────


def run_pure_concolic(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
) -> RunnerResult:
    """Pure concolic — no plugins, engine only."""
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig

    exec_config = ExecutionConfig(
        timeout_seconds=config.timeout,
        solver_timeout=int(config.single_timeout),
        max_iterations=config.max_iterations,
    )
    func = _resolve_target(target)

    start = time.monotonic()
    result = run_concolic(
        func, dict(target.initial_args),
        config=exec_config, isolated=True,
    )
    elapsed = time.monotonic() - start

    return _pyct_result_to_runner(result, func, elapsed)


def run_concolic_llm(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
    seeds: list[dict[str, Any]],
    seed_time: float,
) -> RunnerResult:
    """Concolic + LLM — pre-gen seeds + LLM plugin for plateau/unknown."""
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig
    from pyct.plugins.llm import LLMPlugin
    from pyct.plugins.llm.client import build_default_client

    exec_config = ExecutionConfig(
        timeout_seconds=config.timeout,
        solver_timeout=int(config.single_timeout),
        max_iterations=config.max_iterations,
    )
    func = _resolve_target(target)
    client = build_default_client()
    plugins = [LLMPlugin(client=client)] if client else []

    start = time.monotonic()
    result = run_concolic(
        func, dict(target.initial_args),
        config=exec_config, isolated=False,
        seed_inputs=seeds, plugins=plugins,
    )
    elapsed = time.monotonic() - start + seed_time

    runner_result = _pyct_result_to_runner(result, func, elapsed)
    runner_result.token_usage = _extract_token_usage(plugins)
    return runner_result


def run_llm_only(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
    seeds: list[dict[str, Any]],
    seed_time: float,
) -> RunnerResult:
    """LLM-only — run target on each seed with coverage.py, no engine."""
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))

    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range

    start = time.monotonic()
    hit_lines: set[int] = set()

    for seed in seeds:
        cov.start()
        with contextlib.suppress(Exception):
            func(**seed)
        cov.stop()

        data = cov.get_data()
        for measured_file in data.measured_files():
            if measured_file == target_file:
                hit_lines |= set(data.lines(measured_file) or [])
        cov.erase()

    elapsed = time.monotonic() - start + seed_time

    func_executed = sorted(all_stmts & hit_lines)
    func_missing = sorted(all_stmts - hit_lines)
    total = len(all_stmts)
    pct = (len(func_executed) / total * 100) if total > 0 else 0.0

    return RunnerResult(
        success=True,
        coverage=CoverageResult(
            coverage_percent=pct,
            executed_lines=len(func_executed),
            total_lines=total,
            executed_line_numbers=func_executed,
            missing_line_numbers=func_missing,
        ),
        time_seconds=elapsed,
        iterations=len(seeds),
    )


def run_crosshair(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
) -> RunnerResult:
    """CrossHair — hypothesis-style property testing via subprocess."""
    import subprocess

    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))

    module_func = f"{target.module}.{target.function}"
    cmd = [
        "crosshair", "cover",
        "--per_condition_timeout", str(int(config.timeout)),
        module_func,
    ]

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=config.timeout + 10,
        )
        captured = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return RunnerResult(
            success=False, time_seconds=elapsed,
            error="Crosshair timed out",
        )
    except FileNotFoundError:
        return RunnerResult(
            success=False, error="crosshair not installed",
        )

    elapsed = time.monotonic() - start

    # Measure coverage by running generated inputs
    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range
    hit_lines: set[int] = set()
    inputs_found = _parse_crosshair_cover_output(result.stdout)

    for args, kwargs in inputs_found:
        cov.start()
        with contextlib.suppress(Exception):
            func(*args, **kwargs)
        cov.stop()
        data = cov.get_data()
        for measured_file in data.measured_files():
            if measured_file == target_file:
                hit_lines |= set(data.lines(measured_file) or [])
        cov.erase()

    func_executed = sorted(all_stmts & hit_lines)
    func_missing = sorted(all_stmts - hit_lines)
    total = len(all_stmts)
    pct = (len(func_executed) / total * 100) if total > 0 else 0.0

    return RunnerResult(
        success=True,
        coverage=CoverageResult(
            coverage_percent=pct,
            executed_lines=len(func_executed),
            total_lines=total,
            executed_line_numbers=func_executed,
            missing_line_numbers=func_missing,
        ),
        time_seconds=elapsed,
        iterations=len(inputs_found),
        captured_output=captured,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _resolve_target(target: BenchmarkTarget) -> Callable:
    """Import and return the target callable."""
    module = importlib.import_module(target.module)
    return getattr(module, target.function)


def _pyct_result_to_runner(
    result: Any,
    func: Callable,
    elapsed: float,
) -> RunnerResult:
    """Convert a RunConcolicResult to a RunnerResult with coverage details."""
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))

    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range

    executed = sorted(all_stmts & set(result.executed_lines))
    missing = sorted(all_stmts - set(result.executed_lines))
    total = len(all_stmts)
    pct = (len(executed) / total * 100) if total > 0 else 0.0

    return RunnerResult(
        success=result.success,
        coverage=CoverageResult(
            coverage_percent=pct,
            executed_lines=len(executed),
            total_lines=total,
            executed_line_numbers=executed,
            missing_line_numbers=missing,
        ),
        time_seconds=elapsed,
        error=result.error,
        iterations=result.iterations,
    )


def _extract_token_usage(plugins: list) -> TokenUsage | None:
    """Extract token usage from LLM plugin if available."""
    for plugin in plugins:
        client = getattr(plugin, "_client", None)
        if client is None:
            continue
        stats = getattr(client, "get_stats", None)
        if stats:
            s = stats()
            inp = s.get("input_tokens", 0)
            out = s.get("output_tokens", 0)
            if inp or out:
                return TokenUsage(input_tokens=inp, output_tokens=out)
    return None


def _parse_crosshair_cover_output(
    stdout: str,
) -> list[tuple[list, dict]]:
    """Parse crosshair cover output into (args, kwargs) pairs.

    crosshair cover prints lines like:
        function_name(arg1, arg2, kwarg=value)
    We extract the argument expressions and eval them.
    """
    import ast
    import re

    results: list[tuple[list, dict]] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"\w+\((.*)\)$", line)
        if not match:
            continue
        arg_str = match.group(1)
        if not arg_str:
            results.append(([], {}))
            continue
        try:
            # Parse as a tuple expression to get individual args
            parsed = ast.literal_eval(f"({arg_str},)")
            results.append((list(parsed), {}))
        except (ValueError, SyntaxError):
            log.debug("Could not parse crosshair output: %s", line)
    return results
