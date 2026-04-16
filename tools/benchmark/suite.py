"""Suite orchestrator — retry logic, seed sharing, per-target dispatch."""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any

from tools.benchmark.models import (
    AttemptInfo,
    BenchmarkConfig,
    RunnerResult,
    TokenUsage,
)
from tools.benchmark.runners import (
    CONCOLIC_LLM,
    CROSSHAIR,
    LLM_ONLY,
    PURE_CONCOLIC,
    run_concolic_llm,
    run_crosshair,
    run_llm_only,
    run_pure_concolic,
)
from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.suite")

LLM_RUNNERS = frozenset({LLM_ONLY, CONCOLIC_LLM})


def run_single_target(
    target: BenchmarkTarget,
    runner_names: list[str],
    config: BenchmarkConfig,
    on_runner_done: Any = None,
) -> dict[str, RunnerResult]:
    """Run one target across the requested runners with shared seeds.

    Seeds are generated once and shared between llm_only and concolic_llm.
    Each runner is retried up to config.num_attempts times; best coverage wins.
    """
    seeds, seed_time, seed_tokens = _generate_seeds_if_needed(target, runner_names)

    results: dict[str, RunnerResult] = {}
    for name in runner_names:
        result = _run_with_retries(target, name, config, seeds, seed_time, seed_tokens)
        results[name] = result
        if on_runner_done:
            on_runner_done(name, result)

    return results


def _generate_seeds_if_needed(
    target: BenchmarkTarget,
    runner_names: list[str],
) -> tuple[list[dict[str, Any]], float, TokenUsage | None]:
    """Generate LLM seeds once if any LLM-mode runner is requested.

    Returns (seeds, seed_time, seed_tokens). Token usage from the seed
    generation call is added to both concolic_llm and llm_only results.
    """
    if not LLM_RUNNERS.intersection(runner_names):
        return [], 0.0, None

    from pyct.plugins.llm import LLMPlugin
    from pyct.plugins.llm.client import build_default_client

    client = build_default_client()
    if client is None:
        log.warning("No OpenAI client — LLM modes will run with empty seeds")
        return [], 0.0, None

    plugin = LLMPlugin(client=client)
    ctx = _build_seed_context(target)

    start = time.monotonic()
    seeds = plugin.on_seed_request(ctx)
    seed_time = time.monotonic() - start

    seed_tokens = _tokens_from_client(client)
    log.info("Generated %d seeds for %s in %.1fs", len(seeds), target.name, seed_time)
    return seeds, seed_time, seed_tokens


def _tokens_from_client(client: Any) -> TokenUsage | None:
    """Extract accumulated token usage from an LLM client."""
    get_stats = getattr(client, "get_stats", None)
    if get_stats is None:
        return None
    stats = get_stats()
    inp = stats.get("input_tokens", 0)
    out = stats.get("output_tokens", 0)
    if inp or out:
        return TokenUsage(input_tokens=inp, output_tokens=out)
    return None


def _build_seed_context(target: BenchmarkTarget) -> Any:
    """Build a minimal EngineContext for seed generation."""
    import importlib

    from pyct.config.execution import ExecutionConfig
    from pyct.engine.plugin.context import EngineContext

    module = importlib.import_module(target.module)
    func = getattr(module, target.function)

    return EngineContext(
        iteration=0,
        constraint_pool=(),
        covered_lines=frozenset(),
        total_lines=0,
        inputs_tried=(),
        target_function=func,
        target_signature=inspect.signature(func),
        config=ExecutionConfig(),
        elapsed_seconds=0.0,
    )


def _run_with_retries(
    target: BenchmarkTarget,
    runner_name: str,
    config: BenchmarkConfig,
    seeds: list[dict[str, Any]],
    seed_time: float,
    seed_tokens: TokenUsage | None = None,
) -> RunnerResult:
    """Run a runner up to num_attempts times, keep best coverage."""
    best_result: RunnerResult | None = None
    best_coverage = -1.0
    attempts: list[AttemptInfo] = []

    for run_id in range(config.num_attempts):
        result = _run_single(target, runner_name, config, seeds, seed_time)

        attempts.append(AttemptInfo(
            run_id=run_id,
            coverage=result.coverage.coverage_percent,
            time_seconds=result.time_seconds,
            success=result.success,
            error=result.error,
        ))

        if result.success and result.coverage.coverage_percent > best_coverage:
            best_coverage = result.coverage.coverage_percent
            best_result = result

        if result.success and result.coverage.coverage_percent >= 100.0:
            break

    if best_result is None:
        best_result = RunnerResult(success=False, error="All attempts failed")

    best_result.attempts = attempts

    # Add seed tokens to LLM-mode results
    if runner_name in LLM_RUNNERS and seed_tokens is not None:
        existing = best_result.token_usage
        if existing is not None:
            best_result.token_usage = TokenUsage(
                input_tokens=existing.input_tokens + seed_tokens.input_tokens,
                output_tokens=existing.output_tokens + seed_tokens.output_tokens,
            )
        else:
            best_result.token_usage = seed_tokens

    return best_result


def _run_single(
    target: BenchmarkTarget,
    runner_name: str,
    config: BenchmarkConfig,
    seeds: list[dict[str, Any]],
    seed_time: float,
) -> RunnerResult:
    """Dispatch to the appropriate runner function."""
    try:
        if runner_name == PURE_CONCOLIC:
            return run_pure_concolic(target, config)
        if runner_name == CONCOLIC_LLM:
            return run_concolic_llm(target, config, seeds, seed_time)
        if runner_name == LLM_ONLY:
            return run_llm_only(target, config, seeds, seed_time)
        if runner_name == CROSSHAIR:
            return run_crosshair(target, config)
        return RunnerResult(success=False, error=f"Unknown runner: {runner_name}")
    except Exception as e:
        log.error("Runner %s failed on %s: %s", runner_name, target.name, e)
        return RunnerResult(success=False, error=f"{type(e).__name__}: {e}")
