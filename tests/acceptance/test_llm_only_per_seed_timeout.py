"""``run_llm_only`` must bound per-seed execution with a soft timeout.

Before the fix, ``run_llm_only`` ran every seed in-process with no
watchdog. One slow or non-terminating LLM-generated seed (e.g. the
non-converging while-loop in ``sympy.ntheory.egyptian_fraction.
egypt_takenouchi(15, 7)``) would hang the entire benchmark process.
The concolic runners have line-tracer deadlines + isolated-runner
watchdogs; ``llm_only`` did not.

The fix caps each seed call at ``BenchmarkConfig.single_timeout``
seconds via ``signal.SIGALRM``. Seeds that exceed the budget are
dropped (existing ``contextlib.suppress`` handles the raised
``TimeoutError``) and the runner moves on to the next seed.
"""

from __future__ import annotations

import time


def test_run_llm_only_bounds_slow_seed_by_single_timeout():
    """
    Given a target whose body takes ~10 seconds of pure-Python work
    When run_llm_only is handed two such seeds with single_timeout=1
    Then the total wall-clock elapsed time is well under the seeds'
         combined runtime (~20s) — the per-seed soft timeout must
         interrupt each call close to the 1s budget.
    """
    from tools.benchmark.models import BenchmarkConfig
    from tools.benchmark.runners import run_llm_only
    from tools.benchmark.targets import BenchmarkTarget

    target = BenchmarkTarget(
        name="Slow Spin",
        module="tests.acceptance.fixtures.slow_targets.pure_python_hang",
        function="slow_spin",
        initial_args={"n": 0},
        category="test",
        description="pure-Python spin for the seed-timeout test",
    )
    config = BenchmarkConfig(timeout=60, single_timeout=1, max_iterations=10)
    slow_seeds = [{"n": 10}, {"n": 10}]

    start = time.monotonic()
    result = run_llm_only(target, config, seeds=slow_seeds, seed_time=0.0)
    elapsed = time.monotonic() - start

    # Two seeds @ 1s each + small dispatch overhead → well under 6s.
    # Without the fix, each seed would spin a full 10s (~20s total).
    assert elapsed < 6.0, (
        f"run_llm_only took {elapsed:.1f}s; per-seed soft timeout should "
        "have capped each seed near single_timeout=1s"
    )
    # The runner must still report success — a timed-out seed is a
    # captured exception, not a harness failure.
    assert result.success
