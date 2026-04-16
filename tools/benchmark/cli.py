"""CLI for the benchmark adapter.

Usage:
    python -m tools.benchmark run
    python -m tools.benchmark run --runners pc cl lo
    python -m tools.benchmark run --targets bmi_risk_classifier,triangle_classification
    python -m tools.benchmark run --custom-function mod.path::func_name
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.benchmark.baseline import Baseline
from tools.benchmark.models import BenchmarkConfig, RunnerResult
from tools.benchmark.output import (
    format_comparison_table,
    format_runner_result,
    format_summary_table,
    format_test_header,
    save_results_json,
    save_summary,
)
from tools.benchmark.runners import (
    CONCOLIC_LLM,
    CROSSHAIR,
    LLM_ONLY,
    PURE_CONCOLIC,
    _load_baseline,
)
from tools.benchmark.suite import run_single_target
from tools.benchmark.targets import TEST_SUITE, BenchmarkTarget

log = logging.getLogger("benchmark")

RUNNER_ALIASES = {
    "pc": PURE_CONCOLIC,
    "cl": CONCOLIC_LLM,
    "lo": LLM_ONLY,
    "ch": CROSSHAIR,
    PURE_CONCOLIC: PURE_CONCOLIC,
    CONCOLIC_LLM: CONCOLIC_LLM,
    LLM_ONLY: LLM_ONLY,
    CROSSHAIR: CROSSHAIR,
}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    _load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "baseline":
        from tools.benchmark.baseline_generator import cmd_baseline

        _setup_logging(args.verbose)
        return cmd_baseline(args)

    if args.command != "run":
        parser.print_help()
        return 2

    _setup_logging(args.verbose)

    config = BenchmarkConfig(
        timeout=args.timeout,
        single_timeout=args.single_timeout,
        max_iterations=args.max_iterations,
        num_attempts=args.num_attempts,
        verbose=args.verbose,
        output_dir=args.output_dir,
    )

    runner_names = _resolve_runners(args.runners)
    targets = _resolve_targets(args)

    if not targets:
        print("No targets found.", file=sys.stderr)
        return 1

    run_dir = _create_run_directory(config.output_dir)
    _setup_file_logging(run_dir)

    _output(f"Runners: {', '.join(runner_names)}")
    _output(f"Targets: {len(targets)}")
    _output(f"Attempts: {config.num_attempts}")
    _output("")

    all_results: list[dict[str, Any]] = []

    try:
        for target in targets:
            _output(
                format_test_header(
                    target.name,
                    target.category,
                    target.description,
                    target.function,
                )
            )

            runner_results = run_single_target(
                target,
                runner_names,
                config,
                on_runner_done=lambda name, r: _output(format_runner_result(name, r)),
            )

            _output(format_comparison_table(runner_results))

            result_entry = _build_result_entry(
                target, runner_results, baseline=_load_baseline(target)
            )
            all_results.append(result_entry)

    except KeyboardInterrupt:
        _output("\nBenchmark interrupted.")

    save_results_json(all_results, config, run_dir / "results.json")
    save_summary(all_results, runner_names, run_dir / "summary.txt")

    _output(format_summary_table(all_results, runner_names))
    _output(f"\nResults saved to: {run_dir}")
    return 0


# ── Target resolution ──────────────────────────────────────────────


def _resolve_targets(args: argparse.Namespace) -> list[BenchmarkTarget]:
    """Resolve which targets to run based on CLI args."""
    if args.custom_function:
        return _discover_custom_function(args.custom_function, args.initial_args)

    targets = _discover_suite(args.suite)

    if args.targets:
        names = {t.strip() for t in args.targets.split(",")}
        targets = [t for t in targets if t.function in names]

    if args.category:
        targets = [t for t in targets if t.category == args.category]

    return targets


def _discover_suite(suite: str) -> list[BenchmarkTarget]:
    """Return targets for the requested suite."""
    if suite == "standard":
        return list(TEST_SUITE)

    if suite == "realworld":
        from tools.benchmark.realworld_targets import REALWORLD_SUITE

        return list(REALWORLD_SUITE)

    if suite == "library":
        from tools.benchmark.library_targets import LIBRARY_CONFIGS, discover_library_entry_points

        targets: list[BenchmarkTarget] = []
        for lib_config in LIBRARY_CONFIGS:
            targets.extend(
                discover_library_entry_points(
                    lib_config.package_name,
                    lib_config.category,
                )
            )
        return targets

    if suite == "all":
        from tools.benchmark.library_targets import LIBRARY_CONFIGS, discover_library_entry_points
        from tools.benchmark.realworld_targets import REALWORLD_SUITE

        targets = list(TEST_SUITE) + list(REALWORLD_SUITE)
        for lib_config in LIBRARY_CONFIGS:
            targets.extend(
                discover_library_entry_points(
                    lib_config.package_name,
                    lib_config.category,
                )
            )
        return targets

    _output(f"Unknown suite: {suite}")
    return []


def _discover_custom_function(
    spec: str,
    initial_args_json: str | None,
) -> list[BenchmarkTarget]:
    """Resolve a custom function spec like 'module.path::function_name'."""
    import importlib

    if "::" not in spec:
        print(f"Invalid spec: {spec} (expected module.path::function_name)", file=sys.stderr)
        return []

    module_path, func_name = spec.split("::", 1)
    try:
        module = importlib.import_module(module_path)
        getattr(module, func_name)  # validate it exists
    except (ImportError, AttributeError) as e:
        print(f"Cannot resolve {spec}: {e}", file=sys.stderr)
        return []

    initial_args = {}
    if initial_args_json:
        try:
            initial_args = json.loads(initial_args_json)
        except json.JSONDecodeError as e:
            print(f"Invalid --initial-args JSON: {e}", file=sys.stderr)
            return []

    return [
        BenchmarkTarget(
            name=func_name,
            module=module_path,
            function=func_name,
            initial_args=initial_args,
            category="custom",
            description=f"Custom target: {spec}",
        )
    ]


def _resolve_runners(runner_strs: list[str]) -> list[str]:
    """Resolve runner aliases to full names."""
    result = []
    for r in runner_strs:
        resolved = RUNNER_ALIASES.get(r)
        if resolved is None:
            print(f"Unknown runner: {r}", file=sys.stderr)
            sys.exit(1)
        result.append(resolved)
    return result


# ── Result assembly ────────────────────────────────────────────────


def _build_result_entry(
    target: BenchmarkTarget,
    runner_results: dict[str, RunnerResult],
    baseline: Baseline | None = None,
) -> dict[str, Any]:
    """Build a result dict matching legacy JSON schema + baseline metadata.

    ``baseline_generated_at`` records which frozen baseline scored the
    run (or ``None`` when no baseline was used) so a reviewer can tell
    whether the percentages are still comparable to a later regeneration.
    """
    return {
        "test_name": target.name,
        "function": target.function,
        "category": target.category,
        "baseline_generated_at": baseline.generated_at if baseline else None,
        "runners": {name: r.to_dict() for name, r in runner_results.items()},
    }


# ── Output + logging ──────────────────────────────────────────────


def _output(text: str) -> None:
    """Print to console and log."""
    print(text, flush=True)
    for line in text.splitlines():
        if line.strip():
            log.info(line.strip())


def _setup_logging(verbose: int) -> None:
    """Configure root logger for console output."""
    level = logging.DEBUG if verbose > 0 else logging.INFO
    logging.basicConfig(level=level, format="%(name)s: %(message)s")


def _setup_file_logging(run_dir: Path) -> None:
    """Add a file handler to the benchmark logger."""
    handler = logging.FileHandler(run_dir / "benchmark.log")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger("benchmark").addHandler(handler)


def _create_run_directory(output_dir: str) -> Path:
    """Create a timestamped run directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_dir) / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ── Parser ─────────────────────────────────────────────────────────


def _load_dotenv() -> None:
    """Load .env file if present (for OPENAI_API_KEY)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyct-benchmark",
        description="PyCT benchmark adapter — cross-validation across concolic/LLM/crosshair",
    )
    subs = parser.add_subparsers(dest="command")

    run = subs.add_parser("run", help="Run benchmark suite")
    run.add_argument(
        "--suite",
        default="standard",
        choices=["standard", "realworld", "library", "all"],
        help="Target suite (default: standard)",
    )
    run.add_argument(
        "--runners",
        nargs="+",
        default=["pc", "cl", "lo"],
        help="Runners to invoke (pc=pure_concolic, cl=concolic_llm, lo=llm_only, ch=crosshair)",
    )
    run.add_argument(
        "--targets",
        help="Comma-separated function names to run (default: all 22)",
    )
    run.add_argument(
        "--category",
        help="Filter targets by category",
    )
    run.add_argument(
        "--custom-function",
        help="Custom target: module.path::function_name",
    )
    run.add_argument(
        "--initial-args",
        help="JSON dict of initial args for --custom-function",
    )
    run.add_argument(
        "--num-attempts",
        type=int,
        default=3,
        help="Number of attempts per (target, runner) pair (default: 3)",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Total timeout per exploration run in seconds (default: 60)",
    )
    run.add_argument(
        "--single-timeout",
        type=float,
        default=15.0,
        help="Per-solver-call timeout in seconds (default: 15)",
    )
    run.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Max exploration iterations (default: 50)",
    )
    run.add_argument(
        "--output-dir",
        default="benchmark/results",
        help="Output directory for results (default: benchmark/results)",
    )
    run.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase verbosity",
    )

    baseline = subs.add_parser(
        "baseline",
        help="Generate frozen coverage baselines for library/realworld targets",
    )
    baseline.add_argument(
        "--suite",
        required=True,
        choices=["library", "realworld"],
        help="Target suite to generate baselines for",
    )
    baseline.add_argument(
        "--target",
        help="Substring filter over target names (default: all targets in suite)",
    )
    baseline.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-runner timeout in seconds (default: 120, deliberately higher than run)",
    )
    baseline.add_argument(
        "--single-timeout",
        type=float,
        default=30.0,
        help="Per-solver-call timeout in seconds (default: 30)",
    )
    baseline.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Max exploration iterations per runner (default: 100)",
    )
    baseline.add_argument(
        "--output-dir",
        default="benchmark/baselines",
        help=(
            "Output root (default: benchmark/baselines); baselines land at "
            "{out}/{suite}/{target}.json"
        ),
    )
    baseline.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase verbosity",
    )
    return parser
