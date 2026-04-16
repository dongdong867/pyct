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
        config=exec_config, isolated=True,
        seed_inputs=seeds, plugins=plugins,
    )
    elapsed = time.monotonic() - start + seed_time

    runner_result = _pyct_result_to_runner(result, func, elapsed)
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
    """CrossHair — symbolic execution via ``crosshair cover`` subprocess."""
    import os
    import subprocess

    func = _resolve_target(target)
    target_file = inspect.getfile(func)
    source_lines, start_line = inspect.getsourcelines(func)
    func_range = set(range(start_line, start_line + len(source_lines)))
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

    # Measure coverage by running generated inputs
    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range
    hit_lines: set[int] = set()

    cov.start()
    for inp in test_inputs:
        with contextlib.suppress(Exception):
            func(**inp)
    cov.stop()
    data = cov.get_data()
    for measured_file in data.measured_files():
        if measured_file == target_file:
            hit_lines |= set(data.lines(measured_file) or [])

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
        iterations=len(test_inputs),
        test_cases_generated=len(test_inputs),
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
