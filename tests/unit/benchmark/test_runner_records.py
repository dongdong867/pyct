"""Benchmark runners surface input records and non-execution counters.

The engine's ``inputs_generated`` and counters (``gen_unsat`` /
``gen_unknown`` / ``gen_parse_failed`` / ``harness_error``) flow through
``_pyct_result_to_runner`` into the ``RunnerResult`` so the JSON output
preserves the per-input telemetry.

``run_llm_only`` doesn't run the engine, so it constructs its own
records — one per attempted seed — with provenance ``plugin_seed`` and
outcome derived from coverage delta plus exception text.

``run_crosshair`` is aggregate-only: empty records array plus zeroed
counters. CrossHair has no telemetry to report at the per-input level.
"""

from __future__ import annotations

import signal

import pytest
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import (
    _pyct_result_to_runner,
    run_concolic_llm,
    run_llm_only,
)
from tools.benchmark.targets import BenchmarkTarget

from pyct.engine.result import RunConcolicResult
from pyct.engine.types import InputRecord, Outcome, Provenance


@pytest.fixture
def target() -> BenchmarkTarget:
    return BenchmarkTarget(
        name="classify",
        module="tests.unit.benchmark._fixtures.branching_target",
        function="classify",
        initial_args={"x": 0, "y": 0},
    )


@pytest.fixture
def config() -> BenchmarkConfig:
    return BenchmarkConfig()


class TestPyctResultToRunnerRecords:
    """Engine-backed runners ferry records + counters from RunConcolicResult."""

    def test_records_serialize_to_dicts(self, target):
        rec = InputRecord(
            args={"x": 1, "y": 2},
            provenance=Provenance.SOLVER,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({3, 5}),
            error=None,
        )
        result = RunConcolicResult(
            success=True,
            coverage_percent=50.0,
            executed_lines=frozenset({3, 5}),
            paths_explored=1,
            inputs_generated=(rec,),
            iterations=1,
            termination_reason="exhausted",
        )

        runner_result = _pyct_result_to_runner(result, target, elapsed=1.0)

        assert runner_result.input_records == [
            {
                "args": {"x": 1, "y": 2},
                "provenance": "solver",
                "outcome": "covered_new",
                "new_lines": [3, 5],  # sorted list
                "error": None,
            }
        ]

    def test_counters_propagate_to_runner_result(self, target):
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset(),
            paths_explored=0,
            inputs_generated=(),
            iterations=0,
            termination_reason="exhausted",
            gen_unsat=4,
            gen_unknown=2,
            gen_parse_failed=7,
            harness_error=1,
        )

        runner_result = _pyct_result_to_runner(result, target, elapsed=1.0)

        assert runner_result.gen_unsat == 4
        assert runner_result.gen_unknown == 2
        assert runner_result.gen_parse_failed == 7
        assert runner_result.harness_error == 1

    def test_clean_run_emits_empty_records_and_zero_counters(self, target):
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset(),
            paths_explored=0,
            inputs_generated=(),
            iterations=0,
            termination_reason="exhausted",
        )

        runner_result = _pyct_result_to_runner(result, target, elapsed=0.0)

        assert runner_result.input_records == []
        assert runner_result.gen_unsat == 0
        assert runner_result.gen_unknown == 0
        assert runner_result.gen_parse_failed == 0
        assert runner_result.harness_error == 0


class TestLLMOnlyEmitsRecords:
    """``run_llm_only`` constructs records per attempted seed."""

    def test_one_record_per_seed_with_plugin_seed_provenance(self, target, config):
        seeds = [{"x": 5, "y": 0}, {"x": 0, "y": 5}, {"x": 0, "y": 0}]

        result = run_llm_only(target, config, seeds=seeds, seed_time=0.5)

        assert len(result.input_records) == 3
        for record in result.input_records:
            assert record["provenance"] == "plugin_seed"
        assert [r["args"] for r in result.input_records] == seeds

    def test_records_classify_outcomes_from_coverage_delta(self, target, config):
        # First seed (x=5, y=0): covers `if x > 0` + `return 1` → COVERED_NEW.
        # Second seed (x=5, y=0) duplicate args (rerun): no new lines → NO_GAIN.
        seeds = [{"x": 5, "y": 0}, {"x": 5, "y": 0}]

        result = run_llm_only(target, config, seeds=seeds, seed_time=0.0)

        outcomes = [r["outcome"] for r in result.input_records]
        assert outcomes[0] == "covered_new"
        assert outcomes[1] == "no_gain"

    def test_record_captures_target_error(self, target, config):
        """A seed that raises produces a TARGET_ERROR record with error text."""

        def _crash_target(x: int) -> int:
            raise ValueError(f"bad: {x}")

        # Use a target shadow via monkeypatching the module's classify
        crashy = BenchmarkTarget(
            name="crash",
            module="tests.unit.benchmark._fixtures.branching_target",
            function="classify",
            initial_args={"x": 0, "y": 0},
        )

        # Patch the module's classify to raise
        import tests.unit.benchmark._fixtures.branching_target as fixture_mod

        original = fixture_mod.classify
        fixture_mod.classify = _crash_target  # type: ignore[assignment]
        try:
            result = run_llm_only(crashy, config, seeds=[{"x": 1}], seed_time=0.0)
        finally:
            fixture_mod.classify = original  # type: ignore[assignment]

        assert len(result.input_records) == 1
        record = result.input_records[0]
        assert record["outcome"] == "target_error"
        assert record["error"] is not None
        assert "ValueError" in record["error"]
        assert "bad: 1" in record["error"]

    def test_zero_counters_on_llm_only_run(self, target, config):
        result = run_llm_only(target, config, seeds=[{"x": 0, "y": 0}], seed_time=0.0)

        assert result.gen_unsat == 0
        assert result.gen_unknown == 0
        assert result.gen_parse_failed == 0
        assert result.harness_error == 0


class TestCrossHairAggregateOnly:
    """``run_crosshair`` produces empty records and zero counters."""

    def test_records_empty_and_counters_zero(self, target, config, monkeypatch):
        # Stub the subprocess to return clean output without invoking
        # the real crosshair binary — we only care about the record /
        # counter contract here.
        import subprocess

        from tools.benchmark.runners import run_crosshair

        class _StubResult:
            stdout = ""
            stderr = ""
            returncode = 0

        def fake_run(*args, **kwargs):  # noqa: ARG001
            return _StubResult()

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = run_crosshair(target, config)

        assert result.input_records == []
        assert result.gen_unsat == 0
        assert result.gen_unknown == 0
        assert result.gen_parse_failed == 0
        assert result.harness_error == 0


class TestNonSerializableArgsSanitized:
    """Args carrying non-JSON values fall back to repr in the JSON dict."""

    def test_record_with_unserializable_arg_round_trips(self, target):
        # An object() instance is not JSON-serializable; the record's
        # args dict stores it as-is, and the to_dict serializer relies
        # on the JSON writer's repr fallback to keep it readable.
        sentinel = object()
        rec = InputRecord(
            args={"x": sentinel},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({1}),
            error=None,
        )
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset({1}),
            paths_explored=1,
            inputs_generated=(rec,),
            iterations=1,
            termination_reason="exhausted",
        )

        runner_result = _pyct_result_to_runner(result, target, elapsed=0.0)

        # The record dict preserves args; serialization happens in output.py.
        assert "args" in runner_result.input_records[0]
        assert runner_result.input_records[0]["args"]["x"] is sentinel


class TestBestOfNAttemptIndependence:
    """Each attempt's records belong to that attempt; not aggregated."""

    def test_concolic_llm_records_match_single_run(self, target, config, monkeypatch):
        """Stub run_concolic with two distinct results across attempts;
        the per-attempt RunnerResult must carry only its own attempt's records.
        """

        rec_a = InputRecord(
            args={"x": 1, "y": 0},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({9}),
            error=None,
        )
        rec_b = InputRecord(
            args={"x": 0, "y": 1},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({11}),
            error=None,
        )

        canned = RunConcolicResult(
            success=True,
            coverage_percent=50.0,
            executed_lines=frozenset({9}),
            paths_explored=1,
            inputs_generated=(rec_a,),
            iterations=1,
            termination_reason="exhausted",
        )

        def fake_run_concolic(func, args, *, config, isolated, seed_inputs, plugins):  # noqa: ARG001
            return canned

        monkeypatch.setattr("pyct.run_concolic", fake_run_concolic)

        class _StubClient:
            def get_stats(self) -> dict[str, int]:
                return {"input_tokens": 0, "output_tokens": 0}

        monkeypatch.setattr(
            "pyct.plugins.llm.client.build_default_client",
            lambda: _StubClient(),
        )

        result = run_concolic_llm(target, config, seeds=[{"x": 1, "y": 0}], seed_time=0.0)

        assert len(result.input_records) == 1
        assert result.input_records[0]["args"] == {"x": 1, "y": 0}
        # Confirm rec_b isn't accidentally pulled in from elsewhere.
        assert all(r["args"] != rec_b.args for r in result.input_records), (
            "records must come only from this attempt's RunConcolicResult"
        )


class TestRunnerResultToDict:
    """``RunnerResult.to_dict`` exposes records and counters in JSON shape."""

    def test_to_dict_includes_input_records_field(self, target):
        rec = InputRecord(
            args={"x": 1},
            provenance=Provenance.SEED,
            outcome=Outcome.COVERED_NEW,
            new_lines=frozenset({1}),
            error=None,
        )
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset({1}),
            paths_explored=1,
            inputs_generated=(rec,),
            iterations=1,
            termination_reason="exhausted",
        )
        runner_result = _pyct_result_to_runner(result, target, elapsed=0.0)

        payload = runner_result.to_dict()

        assert "input_records" in payload
        assert payload["input_records"][0]["provenance"] == "seed"

    def test_to_dict_includes_counter_fields(self, target):
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset(),
            paths_explored=0,
            inputs_generated=(),
            iterations=0,
            termination_reason="exhausted",
            gen_unsat=2,
            gen_unknown=3,
            gen_parse_failed=4,
            harness_error=5,
        )
        runner_result = _pyct_result_to_runner(result, target, elapsed=0.0)

        payload = runner_result.to_dict()

        assert payload["gen_unsat"] == 2
        assert payload["gen_unknown"] == 3
        assert payload["gen_parse_failed"] == 4
        assert payload["harness_error"] == 5

    def test_to_dict_includes_outcome_counts_derived_from_records(self, target):
        """``outcome_counts`` is a projection of ``input_records`` — a
        clean exit plus an AssertionError-raising input fold into the
        run-level tally the paper's error-metric table reads."""
        recs = (
            InputRecord(
                args={"x": 1},
                provenance=Provenance.SEED,
                outcome=Outcome.COVERED_NEW,
                new_lines=frozenset({1}),
                error=None,
            ),
            InputRecord(
                args={"x": 2},
                provenance=Provenance.SOLVER,
                outcome=Outcome.TARGET_ERROR,
                new_lines=frozenset(),
                error="AssertionError: x must be positive",
            ),
        )
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset({1}),
            paths_explored=1,
            inputs_generated=recs,
            iterations=2,
            termination_reason="exhausted",
        )
        runner_result = _pyct_result_to_runner(result, target, elapsed=0.0)

        payload = runner_result.to_dict()

        assert payload["outcome_counts"] == {
            "total": 2,
            "clean_exit": 1,
            "error_exit": 1,
            "timeout": 0,
            "by_exception": {"AssertionError": 1},
        }


# Skip on Windows or systems without SIGALRM (run_llm_only uses _soft_timeout).
pytestmark = pytest.mark.skipif(
    not hasattr(signal, "SIGALRM"),
    reason="run_llm_only's soft timeout requires SIGALRM",
)
