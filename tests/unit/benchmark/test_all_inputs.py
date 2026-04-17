"""Input composition for baseline generation.

Baselines were empty for targets where neither concolic nor crosshair
could discover inputs (urllib.parse.urlsplit, urlencode, urlquote,
parse_qs). Fix: always seed with ``target.initial_args`` so the happy
path is exercised even when the discovery tools turn up nothing.
"""

from __future__ import annotations

import pytest
from tools.benchmark.baseline_generator import _all_inputs
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.targets import BenchmarkTarget


@pytest.fixture
def target() -> BenchmarkTarget:
    return BenchmarkTarget(
        name="t",
        module="m",
        function="f",
        initial_args={"x": 42, "name": "hello"},
    )


@pytest.fixture
def config() -> BenchmarkConfig:
    return BenchmarkConfig()


def test_first_input_is_always_the_targets_initial_args(monkeypatch, target, config):
    # Pretend concolic and crosshair both fail to produce anything.
    monkeypatch.setattr("tools.benchmark.baseline_generator.concolic_inputs", lambda *_: [])
    monkeypatch.setattr("tools.benchmark.baseline_generator.crosshair_inputs", lambda *_: [])

    inputs = _all_inputs(target, config)

    assert inputs == [{"x": 42, "name": "hello"}]


def test_extends_with_concolic_and_crosshair_inputs(monkeypatch, target, config):
    monkeypatch.setattr(
        "tools.benchmark.baseline_generator.concolic_inputs",
        lambda *_: [{"x": 1, "name": "a"}, {"x": 2, "name": "b"}],
    )
    monkeypatch.setattr(
        "tools.benchmark.baseline_generator.crosshair_inputs",
        lambda *_: [{"x": 99, "name": "c"}],
    )

    inputs = _all_inputs(target, config)

    # initial_args first, then concolic, then crosshair — order preserved
    # for deterministic coverage collection.
    assert inputs == [
        {"x": 42, "name": "hello"},
        {"x": 1, "name": "a"},
        {"x": 2, "name": "b"},
        {"x": 99, "name": "c"},
    ]


def test_initial_args_copy_is_isolated_from_target(monkeypatch, target, config):
    # A consumer that mutates the returned inputs must not mutate the target.
    monkeypatch.setattr("tools.benchmark.baseline_generator.concolic_inputs", lambda *_: [])
    monkeypatch.setattr("tools.benchmark.baseline_generator.crosshair_inputs", lambda *_: [])

    inputs = _all_inputs(target, config)
    inputs[0]["x"] = 999

    assert target.initial_args["x"] == 42
