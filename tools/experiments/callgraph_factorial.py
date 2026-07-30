"""Measure the marginal effect of each static-analysis prompt block.

The engine seeds from source + signature only. This experiment restores
the legacy call-graph and CFG blocks behind
:class:`PromptContextOptions` and measures what each one buys, holding
everything downstream identical: same targets, same engine config, same
concolic run, same coverage measurement. Only the seed prompt varies.

Arms are chosen so each block can be read on its own — ``callees``
against ``none`` gives the callee-source effect, ``cfg`` against
``none`` the CFG effect, and ``callees+bounds`` against ``callees``
isolates extracted literals, which include return-value strings and may
well hurt.

Run::

    uv run python -m tools.experiments.callgraph_factorial --trials 3
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import run_concolic_llm
from tools.benchmark.suite import _build_seed_context
from tools.benchmark.targets import TEST_SUITE, BenchmarkTarget

from pyct.plugins.llm import LLMPlugin
from pyct.plugins.llm.client import build_default_client
from pyct.plugins.llm.prompt import PromptContextOptions

log = logging.getLogger("experiment.callgraph")

# Callee-heavy standard targets: the regime where hidden branch
# predicates should matter most. Results are an upper bound on the
# effect across the full suite, not an estimate of it.
TARGET_NAMES = (
    "Semver Parsing",
    "URL Routing",
    "Log Level Routing",
    "Multi-Stage Form Validation",
)

ARMS: dict[str, PromptContextOptions | None] = {
    "none": None,
    "cfg": PromptContextOptions(include_cfg=True),
    "callees": PromptContextOptions(include_callees=True),
    "callees+cfg": PromptContextOptions(include_callees=True, include_cfg=True),
    "callees+bounds": PromptContextOptions(
        include_callees=True, include_boundary_values=True
    ),
}


@dataclass
class TrialRecord:
    """One (target, arm, trial) measurement."""

    target: str
    arm: str
    trial: int
    coverage: float
    seed_count: int
    prompt_chars: int
    seed_tokens: int
    elapsed: float


def _targets() -> list[BenchmarkTarget]:
    by_name = {t.name: t for t in TEST_SUITE}
    missing = [n for n in TARGET_NAMES if n not in by_name]
    if missing:
        raise SystemExit(f"unknown target names: {missing}")
    return [by_name[n] for n in TARGET_NAMES]


def _generate_seeds(
    target: BenchmarkTarget,
    options: PromptContextOptions | None,
) -> tuple[list[dict[str, Any]], float, int, int]:
    """Seed once under *options*. Returns (seeds, secs, prompt_chars, tokens)."""
    from pyct.plugins.llm.prompt import build_seed_prompt

    client = build_default_client()
    if client is None:
        raise SystemExit("OPENAI_API_KEY missing — cannot run the experiment")

    ctx = _build_seed_context(target)
    prompt_chars = len(build_seed_prompt(ctx, options))

    plugin = LLMPlugin(client=client, context_options=options)
    start = time.monotonic()
    seeds = plugin.on_seed_request(ctx)
    elapsed = time.monotonic() - start

    stats = getattr(client, "get_stats", lambda: {})() or {}
    tokens = stats.get("input_tokens", 0) + stats.get("output_tokens", 0)
    return seeds, elapsed, prompt_chars, tokens


def _run_trial(
    target: BenchmarkTarget,
    arm: str,
    trial: int,
    config: BenchmarkConfig,
) -> TrialRecord:
    """Seed under *arm*, then explore and measure coverage."""
    seeds, seed_time, prompt_chars, tokens = _generate_seeds(target, ARMS[arm])
    result = run_concolic_llm(target, config, seeds, seed_time)
    return TrialRecord(
        target=target.name,
        arm=arm,
        trial=trial,
        coverage=result.coverage.percent,
        seed_count=len(seeds),
        prompt_chars=prompt_chars,
        seed_tokens=tokens,
        elapsed=result.elapsed_seconds,
    )


def _summarize(records: list[TrialRecord]) -> dict[str, dict[str, float]]:
    """Mean coverage and prompt size per arm, plus delta against ``none``."""
    summary: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        rows = [r for r in records if r.arm == arm]
        if not rows:
            continue
        summary[arm] = {
            "mean_coverage": statistics.mean(r.coverage for r in rows),
            "mean_prompt_chars": statistics.mean(r.prompt_chars for r in rows),
            "mean_seed_tokens": statistics.mean(r.seed_tokens for r in rows),
            "mean_seeds": statistics.mean(r.seed_count for r in rows),
            "n": len(rows),
        }
    baseline = summary.get("none", {}).get("mean_coverage")
    if baseline is not None:
        for arm, stats in summary.items():
            stats["delta_pp"] = stats["mean_coverage"] - baseline
    return summary


def _print_report(records: list[TrialRecord], summary: dict[str, Any]) -> None:
    print("\n=== Per-target mean coverage (%) ===")
    header = f"{'target':<30}" + "".join(f"{a:>16}" for a in ARMS)
    print(header)
    for name in TARGET_NAMES:
        cells = []
        for arm in ARMS:
            rows = [r for r in records if r.target == name and r.arm == arm]
            cells.append(f"{statistics.mean(r.coverage for r in rows):>16.1f}" if rows else f"{'-':>16}")
        print(f"{name:<30}" + "".join(cells))

    print("\n=== Arm summary ===")
    print(f"{'arm':<18}{'coverage':>10}{'delta_pp':>10}{'prompt_ch':>12}{'tokens':>10}{'seeds':>8}")
    for arm, s in summary.items():
        print(
            f"{arm:<18}{s['mean_coverage']:>10.1f}{s.get('delta_pp', 0.0):>+10.2f}"
            f"{s['mean_prompt_chars']:>12.0f}{s['mean_seed_tokens']:>10.0f}{s['mean_seeds']:>8.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out", default="benchmark/results/callgraph_factorial.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    config = BenchmarkConfig(timeout=args.timeout, num_attempts=1)

    records: list[TrialRecord] = []
    targets = _targets()
    total = len(targets) * len(ARMS) * args.trials
    done = 0
    for target in targets:
        for arm in ARMS:
            for trial in range(args.trials):
                done += 1
                print(f"[{done}/{total}] {target.name} | {arm} | trial {trial + 1}", flush=True)
                try:
                    records.append(_run_trial(target, arm, trial, config))
                except Exception as exc:  # noqa: BLE001 - one bad cell must not end the run
                    log.warning("FAILED %s/%s/%d: %s", target.name, arm, trial, exc)

    summary = _summarize(records)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"records": [r.__dict__ for r in records], "summary": summary},
            indent=2,
        )
    )
    _print_report(records, summary)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
