"""Baseline generation — run a target with diverse inputs, freeze the entered scopes.

The generator widens coverage.py's measurement scope to the target's
package (via ``target.source_path``) so sub-callees are measured, not
just the entry function. Inputs are drawn from pure_concolic and
crosshair (deterministic, no API cost); the union of their entered
functions becomes the target's frozen denominator.

This module intentionally does NOT use LLM runners for baseline
generation — the baseline is meant to be a stable, reproducible
artifact, and LLM non-determinism would drift across regenerations.

Pure data-shape helpers live in :mod:`tools.benchmark.baseline`.
The ``cmd_baseline`` entry point backs the ``python -m tools.benchmark
baseline`` CLI subcommand.
"""

from __future__ import annotations

import contextlib
import inspect
import logging
from datetime import datetime
from typing import Any

from coverage import Coverage

from pyct.utils.call_binding import call_with_args
from tools.benchmark.baseline import (
    Baseline,
    FunctionScope,
    build_baseline,
    scopes_from_coverage_session,
)
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import (
    _parse_crosshair_output,
    _resolve_target,
    _suppress_output,
)
from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.baseline")


def baseline_session_for_target(target: BenchmarkTarget) -> Coverage:
    """Coverage session wide enough to see the target's sub-callees.

    When ``target.source_path`` is set (library / realworld), measure
    every file under that directory so deep-callee hits are recorded.
    Without a source_path, fall back to file-scoped measurement — the
    standard suite never sees this path, but it keeps the function
    total for ad-hoc use.
    """
    if target.source_path:
        return Coverage(data_file=None, source=[target.source_path])
    func = _resolve_target(target)
    target_file = inspect.getfile(inspect.unwrap(func))
    return Coverage(data_file=None, include=[target_file])


def collect_scopes_for_inputs(
    target: BenchmarkTarget,
    inputs: list[dict[str, Any]],
) -> list[FunctionScope]:
    """Run every input under one broad coverage session; extract scopes.

    Inputs that raise (wrong type, library refuses to parse) are
    swallowed — one bad input must not sink the whole collection.
    Returned scopes retain absolute file paths; callers apply
    ``normalize_scope_paths`` before serialization.
    """
    func = _resolve_target(target)
    cov = baseline_session_for_target(target)

    cov.start()
    for inp in inputs:
        with _suppress_output(), contextlib.suppress(Exception):
            call_with_args(func, inp)
    cov.stop()

    return scopes_from_coverage_session(cov)


def concolic_inputs(target: BenchmarkTarget, config: BenchmarkConfig) -> list[dict[str, Any]]:
    """Inputs discovered by pyct's concolic engine on ``target``."""
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig

    exec_config = ExecutionConfig(
        timeout_seconds=config.timeout,
        solver_timeout=int(config.single_timeout),
        max_iterations=config.max_iterations,
    )
    func = _resolve_target(target)

    try:
        result = run_concolic(
            func,
            dict(target.initial_args),
            config=exec_config,
            isolated=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("concolic failed for %s: %s", target.name, exc)
        return []

    return list(result.inputs_generated)


def crosshair_inputs(target: BenchmarkTarget, config: BenchmarkConfig) -> list[dict[str, Any]]:
    """Inputs suggested by ``crosshair cover`` subprocess for ``target``."""
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

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout + 10,
            cwd=os.getcwd(),
            env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("crosshair unavailable for %s: %s", target.name, exc)
        return []

    return _parse_crosshair_output(
        completed.stdout + "\n" + completed.stderr, func.__name__, param_names
    )


def generate_baseline(
    target: BenchmarkTarget,
    config: BenchmarkConfig,
    now: datetime | None = None,
) -> Baseline:
    """Produce a frozen Baseline by unioning concolic + crosshair entered scopes.

    Runs each input source in turn (failures logged and skipped), then
    exercises every collected input under a single broad coverage
    session so both sources' coverage lands in one place. The result is
    path-normalized and stamped with ``now`` as the ISO timestamp.
    """
    when = now or datetime.now()
    log.info("generating baseline for %s", target.name)

    all_inputs: list[dict[str, Any]] = []
    all_inputs.extend(concolic_inputs(target, config))
    all_inputs.extend(crosshair_inputs(target, config))

    if not all_inputs:
        log.warning("no inputs discovered for %s — baseline will be empty", target.name)

    scopes = collect_scopes_for_inputs(target, all_inputs)
    return build_baseline(target.name, [scopes], when)


# ── CLI ────────────────────────────────────────────────────────────


def cmd_baseline(args: Any) -> int:
    """Generate + persist baselines for every target in the chosen suite.

    Writes one JSON per target to
    ``{output_dir}/{suite}/{target.name}.json``. Errors on individual
    targets are logged and skipped — partial progress is better than
    aborting a multi-hour run on one flaky target.
    """
    from pathlib import Path

    targets = _targets_for_suite(args.suite)
    if args.target:
        needle = args.target
        targets = [t for t in targets if needle in t.name]
    if not targets:
        log.error("no targets matched suite=%s target=%s", args.suite, args.target)
        return 1

    config = BenchmarkConfig(
        timeout=args.timeout,
        single_timeout=args.single_timeout,
        max_iterations=args.max_iterations,
    )
    out_root = Path(args.output_dir) / args.suite
    out_root.mkdir(parents=True, exist_ok=True)

    total = len(targets)
    for idx, target in enumerate(targets, 1):
        log.info("[%d/%d] %s", idx, total, target.name)
        try:
            baseline = generate_baseline(target, config)
        except Exception as exc:  # noqa: BLE001
            log.error("failed to generate baseline for %s: %s", target.name, exc)
            continue
        out_path = out_root / f"{target.name}.json"
        baseline.to_json(out_path)
        log.info(
            "  wrote %s (%d scopes, %d lines)",
            out_path,
            len(baseline.scopes),
            baseline.total_lines,
        )

    return 0


def _targets_for_suite(suite: str) -> list[BenchmarkTarget]:
    """Load targets for a named suite, matching the CLI's ``run`` wiring."""
    if suite == "library":
        from tools.benchmark.library_targets import (
            LIBRARY_CONFIGS,
            discover_library_entry_points,
        )

        targets: list[BenchmarkTarget] = []
        for cfg in LIBRARY_CONFIGS:
            targets.extend(discover_library_entry_points(cfg.package_name, cfg.category))
        return targets
    if suite == "realworld":
        from tools.benchmark.realworld_targets import REALWORLD_SUITE

        return list(REALWORLD_SUITE)
    raise ValueError(f"unsupported suite for baseline generation: {suite!r}")
