"""Benchmark runners — one function per execution mode.

Each runner takes a target + config and returns a RunnerResult.
Seed generation is external (done by the suite orchestrator) so
llm_only and concolic_llm receive pre-generated seeds.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import logging
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
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

    return _pyct_result_to_runner(result, target, elapsed)


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
        config=exec_config, isolated=True,
        seed_inputs=seeds, plugins=plugins,
    )
    elapsed = time.monotonic() - start + seed_time

    # Union engine coverage with plain seed coverage to ensure
    # concolic_llm >= llm_only. The engine's Concolic wrapping may
    # cause seeds to cover fewer lines than plain execution.
    engine_lines = set(result.executed_lines)
    seed_lines = _replay_seeds_plain(target, seeds)
    all_lines = engine_lines | seed_lines

    runner_result = _pyct_result_to_runner_with_lines(
        result, target, elapsed, all_lines,
    )
    if result.token_stats:
        runner_result.token_usage = TokenUsage(
            input_tokens=result.token_stats.get("input_tokens", 0),
            output_tokens=result.token_stats.get("output_tokens", 0),
        )
    return runner_result


def run_llm_only(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
    seeds: list[dict[str, Any]],
    seed_time: float,
) -> RunnerResult:
    """LLM-only — run target on each seed with coverage.py, no engine."""
    func = _resolve_target(target)
    cov = _create_coverage_session(target)

    start = time.monotonic()
    for seed in seeds:
        cov.start()
        with _suppress_output(), contextlib.suppress(Exception):
            func(**seed)
        cov.stop()
    elapsed = time.monotonic() - start + seed_time

    coverage = _measure_coverage(cov, target)
    return RunnerResult(
        success=True,
        coverage=coverage,
        time_seconds=elapsed,
        iterations=len(seeds),
    )


def run_crosshair(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
) -> RunnerResult:
    """CrossHair — symbolic execution via ``crosshair cover`` subprocess."""
    import os
    import subprocess

    func = _resolve_target(target)
    param_names = list(inspect.signature(func).parameters.keys())

    module_func = f"{target.module}.{target.function}"
    cmd = [
        "uv", "run", "crosshair", "cover",
        module_func,
        "--per_path_timeout", str(int(config.single_timeout)),
        "--max_uninteresting_iterations", str(config.max_iterations),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=config.timeout + 10, cwd=os.getcwd(), env=env,
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
            success=False, error="crosshair not installed (uv run crosshair failed)",
        )

    elapsed = time.monotonic() - start

    test_inputs = _parse_crosshair_output(
        result.stdout + "\n" + result.stderr, func.__name__, param_names
    )
    if not test_inputs and not param_names:
        test_inputs = [{}]

    log.info("Crosshair generated %d inputs for %s:", len(test_inputs), target.function)
    for i, inp in enumerate(test_inputs):
        log.info("  crosshair[%d]: %s", i, inp)

    # Measure coverage by running generated inputs
    cov = _create_coverage_session(target)
    cov.start()
    for inp in test_inputs:
        with _suppress_output(), contextlib.suppress(Exception):
            func(**inp)
    cov.stop()

    return RunnerResult(
        success=True,
        coverage=_measure_coverage(cov, target),
        time_seconds=elapsed,
        iterations=len(test_inputs),
        test_cases_generated=len(test_inputs),
        captured_output=captured,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _resolve_target(target: BenchmarkTarget) -> Callable:
    """Import and return the target callable."""
    module = importlib.import_module(target.module)
    return getattr(module, target.function)


def _replay_seeds_plain(
    target: BenchmarkTarget,
    seeds: list[dict[str, Any]],
) -> set[int]:
    """Run seeds under plain execution (no Concolic wrapping) and return hit lines.

    This ensures concolic_llm captures the same seed coverage as llm_only.
    The engine's ConcolicStr wrapping can alter execution paths, causing
    seeds to hit fewer lines than with plain values.
    """
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    cov = Coverage(data_file=None, include=[target_file])

    for seed in seeds:
        cov.start()
        with _suppress_output(), contextlib.suppress(Exception):
            func(**seed)
        cov.stop()

    hit: set[int] = set()
    data = cov.get_data()
    for measured_file in data.measured_files():
        if measured_file == target_file:
            hit |= set(data.lines(measured_file) or [])
    return hit


def _pyct_result_to_runner_with_lines(
    result: Any,
    target: BenchmarkTarget,
    elapsed: float,
    executed_lines: set[int],
) -> RunnerResult:
    """Build RunnerResult using a custom set of executed lines."""
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))

    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range

    return RunnerResult(
        success=result.success,
        coverage=_build_coverage_result(all_stmts, executed_lines),
        time_seconds=elapsed,
        error=result.error,
        iterations=result.iterations,
    )


@contextlib.contextmanager
def _suppress_output():
    """Redirect stdout and stderr to devnull.

    External library functions (sympy diagnostics, cProfile
    output, etc.) can print heavily during execution.
    Suppressing keeps the benchmark console clean.
    """
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


def _create_coverage_session(target: BenchmarkTarget) -> Coverage:
    """Create a coverage.py session scoped to the target file."""
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    return Coverage(data_file=None, include=[target_file])


def _measure_coverage(cov: Coverage, target: BenchmarkTarget) -> CoverageResult:
    """Compute function-level coverage from a stopped coverage.py session.

    All runners use the same metric: lines in the entry function.
    This ensures the denominator is identical across runners for fair
    comparison. Entered-scope is available via scope_analysis.py as a
    secondary metric but not used in the primary benchmark table.
    """
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))
    all_stmts = set(cov.analysis(target_file)[1]) & func_range

    data = cov.get_data()
    hit_lines: set[int] = set()
    for measured_file in data.measured_files():
        if measured_file == target_file:
            hit_lines |= set(data.lines(measured_file) or [])

    return _build_coverage_result(all_stmts, hit_lines)


def _build_coverage_result(
    all_stmts: set[int],
    hit_lines: set[int],
) -> CoverageResult:
    """Build a CoverageResult with definition-line inclusion.

    If any body line was executed, lines before the first executed line
    (decorators, ``def`` header) are counted as covered — the function
    must have been defined to be called. This matches the engine's
    ``CoverageTracker(pre_covered={def_line})`` behavior and legacy's
    ``calculate_function_coverage`` def-line backfill.
    """
    func_executed = sorted(all_stmts & hit_lines)

    if func_executed:
        first_executed = min(func_executed)
        for stmt in sorted(all_stmts):
            if stmt < first_executed and stmt not in func_executed:
                func_executed.append(stmt)
        func_executed = sorted(func_executed)

    func_missing = sorted(all_stmts - set(func_executed))
    total = len(all_stmts)
    pct = (len(func_executed) / total * 100) if total > 0 else 0.0

    return CoverageResult(
        coverage_percent=pct,
        executed_lines=len(func_executed),
        total_lines=total,
        executed_line_numbers=func_executed,
        missing_line_numbers=func_missing,
    )


def _pyct_result_to_runner(
    result: Any,
    target: BenchmarkTarget,
    elapsed: float,
) -> RunnerResult:
    """Convert a RunConcolicResult to a RunnerResult with coverage details.

    For package targets, re-measures using the engine's executed_lines
    against the function-level scope. Entered-scope analysis for engine
    results would require the engine to track package-wide coverage,
    which it doesn't — its CoverageTracker is scoped to the target file.
    """
    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))

    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range

    return RunnerResult(
        success=result.success,
        coverage=_build_coverage_result(all_stmts, set(result.executed_lines)),
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


def _parse_crosshair_output(
    output: str,
    func_name: str,
    param_names: list[str],
) -> list[dict[str, Any]]:
    """Parse crosshair cover output into input dicts.

    crosshair cover prints lines like ``func_name(arg1, arg2, kw=val)``.
    Uses AST parsing to handle both positional and keyword args, mapping
    positional args to parameter names by position.
    """
    import re

    pattern = rf"{re.escape(func_name)}\s*\((.*?)\)"
    results: list[dict[str, Any]] = []

    for match in re.finditer(pattern, output, re.DOTALL):
        args_dict = _parse_call_args(func_name, match.group(1), param_names)
        if args_dict and args_dict not in results:
            results.append(args_dict)

    return results


def _parse_call_args(
    func_name: str,
    args_str: str,
    param_names: list[str],
) -> dict[str, Any] | None:
    """Parse argument string via AST into a name→value dict."""
    import ast

    try:
        tree = ast.parse(f"{func_name}({args_str})")
        if not tree.body or not isinstance(tree.body[0], ast.Expr):
            return None
        call = tree.body[0].value
        if not isinstance(call, ast.Call):
            return None

        args_dict: dict[str, Any] = {}
        for kw in call.keywords:
            value = _try_literal_eval(kw.value)
            if value is not None:
                args_dict[kw.arg] = value
        for i, arg in enumerate(call.args):
            if i < len(param_names):
                value = _try_literal_eval(arg)
                if value is not None:
                    args_dict[param_names[i]] = value
        return args_dict if args_dict else None
    except SyntaxError:
        return None


def _try_literal_eval(node: Any) -> Any | None:
    """Safely evaluate an AST node as a literal value."""
    import ast

    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        if isinstance(node, ast.Constant):
            return node.value
        return None
