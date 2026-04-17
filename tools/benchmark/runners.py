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
import json
import logging
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from coverage import Coverage

from pyct.utils.call_binding import call_with_args
from tools.benchmark.baseline import BASELINE_SCHEMA_VERSION, Baseline
from tools.benchmark.models import (
    BenchmarkConfig,
    CoverageResult,
    RunnerResult,
    TokenUsage,
)
from tools.benchmark.targets import BenchmarkTarget

_DEFAULT_BASELINES_ROOT = Path("benchmark/baselines")

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
        func,
        dict(target.initial_args),
        config=exec_config,
        isolated=True,
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
        func,
        dict(target.initial_args),
        config=exec_config,
        isolated=True,
        seed_inputs=seeds,
        plugins=plugins,
    )
    elapsed = time.monotonic() - start + seed_time

    runner_result = _pyct_result_to_runner(result, target, elapsed)
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
    """LLM-only — run target on each seed with coverage.py, no engine.

    Each seed is capped at ``config.single_timeout`` wall-clock seconds
    via a SIGALRM-based soft timeout. A pathological seed (e.g. a
    non-converging loop in ``sympy.ntheory.egyptian_fraction.
    egypt_takenouchi(15, 7)``) would otherwise hang the benchmark
    indefinitely — the concolic runners are protected by the engine's
    line-tracer deadline and the isolated-runner watchdog, but this
    path runs targets in-process.
    """
    func = _resolve_target(target)
    cov = _create_coverage_session(target)
    per_seed_budget = max(1, int(config.single_timeout))

    start = time.monotonic()
    for seed in seeds:
        cov.start()
        with _suppress_output(), _soft_timeout(per_seed_budget), contextlib.suppress(Exception):
            call_with_args(func, seed)
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
        "uv",
        "run",
        "crosshair",
        "cover",
        module_func,
        "--per_path_timeout",
        str(int(config.single_timeout)),
        "--max_uninteresting_iterations",
        str(config.max_iterations),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout + 10,
            cwd=os.getcwd(),
            env=env,
        )
        captured = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return RunnerResult(
            success=False,
            time_seconds=elapsed,
            error="Crosshair timed out",
        )
    except FileNotFoundError:
        return RunnerResult(
            success=False,
            error="crosshair not installed (uv run crosshair failed)",
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
            call_with_args(func, inp)
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


@contextlib.contextmanager
def _suppress_output():
    """Redirect stdout and stderr to devnull.

    External library functions (sympy diagnostics, cProfile
    output, etc.) can print heavily during execution.
    Suppressing keeps the benchmark console clean.
    """
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


@contextlib.contextmanager
def _soft_timeout(seconds: int):
    """Install a SIGALRM-based soft timeout for the enclosed block.

    On Unix, schedules an alarm that raises ``TimeoutError`` after
    ``seconds`` if the block is still running. The previous handler
    and alarm are restored on exit. No-op on platforms without
    ``SIGALRM`` (Windows) or when invoked off the main thread —
    Python only delivers signals to the main thread.

    SIGALRM interrupts Python bytecode at frame boundaries, so it
    cleanly stops pure-Python hangs. It cannot preempt code blocked
    inside a C extension (e.g. ``[y] * 10**9`` stuck in
    ``list.__mul__``); those rare cases would require full
    subprocess isolation.
    """
    import signal
    import threading

    alarm = getattr(signal, "SIGALRM", None)
    if alarm is None or threading.current_thread() is not threading.main_thread():
        yield
        return

    def _raise(_signum, _frame):
        raise TimeoutError(f"seed exceeded {seconds}s soft timeout")

    previous = signal.signal(alarm, _raise)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(alarm, previous)


def _load_baseline(
    target: BenchmarkTarget,
    baselines_root: Path | None = None,
) -> Baseline | None:
    """Look up a frozen baseline for ``target``, or return ``None``.

    Searches ``{root}/*/{target.name}.json`` — generator output is
    partitioned by suite but callers don't need to know which. Returns
    ``None`` (never raises) if the root is missing, the JSON is
    malformed, required keys are absent, or the schema version differs
    from what this code understands — runners fall back to function-
    scope measurement in any of those cases so a botched baseline
    never sinks a benchmark run.
    """
    root = baselines_root or _DEFAULT_BASELINES_ROOT
    if not root.is_dir():
        return None

    for candidate in root.glob(f"*/{target.name}.json"):
        try:
            baseline = Baseline.from_json(candidate)
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            log.warning("failed to load baseline %s: %s", candidate, exc)
            continue
        if baseline.generator_version != BASELINE_SCHEMA_VERSION:
            log.warning(
                "baseline %s has unsupported schema version %s (expected %s)",
                candidate,
                baseline.generator_version,
                BASELINE_SCHEMA_VERSION,
            )
            continue
        return baseline

    return None


def _create_coverage_session(target: BenchmarkTarget) -> Coverage:
    """Create a coverage.py session scoped appropriately for ``target``.

    When ``target.source_path`` is set (library / realworld), widen to
    measure every file under the package root so sub-callees are
    captured. Otherwise scope narrowly to the target's own file — the
    standard suite uses function-scope coverage and doesn't need
    package-wide measurement.
    """
    if target.source_path:
        return Coverage(data_file=None, source=[target.source_path])
    func = _resolve_target(target)
    target_file = inspect.getfile(inspect.unwrap(func))
    return Coverage(data_file=None, include=[target_file])


def _measure_coverage(
    cov: Coverage,
    target: BenchmarkTarget,
    baselines_root: Path | None = None,
) -> CoverageResult:
    """Compute coverage from a stopped coverage.py session.

    Dispatch: if a frozen baseline exists for the target, score against
    it (same denominator for every runner). Otherwise fall back to
    function-scope on the entry file — preserves current behavior for
    the standard suite and for library/realworld targets whose
    baselines haven't been committed yet.
    """
    baseline = _load_baseline(target, baselines_root)
    if baseline is not None:
        from tools.benchmark.baseline import (
            hits_from_coverage_data,
            measure_against_baseline,
        )

        hits = hits_from_coverage_data(cov.get_data())
        return measure_against_baseline(hits, baseline)

    func = _resolve_target(target)
    unwrapped = inspect.unwrap(func)
    target_file = inspect.getfile(unwrapped)
    source_lines, start_line = inspect.getsourcelines(unwrapped)
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

    Two measurement paths:

    - ``target.source_path`` set (library / realworld): re-run the
      engine's ``inputs_generated`` through a broad coverage.py session
      so sub-callees are actually measured. The engine's own tracker is
      scoped to the target file and cannot see transitive coverage.
    - ``source_path`` unset (standard): use the engine's
      ``executed_lines`` directly against the function-level scope —
      preserves comparability with the pre-baseline paper numbers.
    """
    if target.source_path:
        coverage = _coverage_by_rerun(target, result.inputs_generated)
    else:
        coverage = _coverage_from_engine_tracker(target, result.executed_lines)

    return RunnerResult(
        success=result.success,
        coverage=coverage,
        time_seconds=elapsed,
        error=result.error,
        iterations=result.iterations,
    )


_RERUN_SOFT_TIMEOUT_SECONDS = 15


def _coverage_by_rerun(
    target: BenchmarkTarget,
    inputs: Any,
) -> CoverageResult:
    """Replay ``inputs`` under a broad coverage session, then measure.

    Each input gets a SIGALRM-based soft timeout so a pathological case
    (e.g. ``sympy.ntheory.egyptian_fraction.egypt_takenouchi(15, 7)``)
    can't hang the in-process re-execution — the same protection
    :func:`run_llm_only` already has.
    """
    func = _resolve_target(target)
    cov = _create_coverage_session(target)
    cov.start()
    for inp in inputs:
        with (
            _suppress_output(),
            _soft_timeout(_RERUN_SOFT_TIMEOUT_SECONDS),
            contextlib.suppress(Exception),
        ):
            call_with_args(func, inp)
    cov.stop()
    return _measure_coverage(cov, target)


def _coverage_from_engine_tracker(
    target: BenchmarkTarget,
    executed_lines: Any,
) -> CoverageResult:
    """Function-scope coverage using the engine's per-line tracker."""
    func = _resolve_target(target)
    unwrapped = inspect.unwrap(func)
    target_file = inspect.getfile(unwrapped)
    source_lines, start_line = inspect.getsourcelines(unwrapped)
    func_range = set(range(start_line, start_line + len(source_lines)))
    cov = Coverage(data_file=None, include=[target_file])
    all_stmts = set(cov.analysis(target_file)[1]) & func_range
    return _build_coverage_result(all_stmts, set(executed_lines))


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
