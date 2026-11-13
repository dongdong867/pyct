"""``pyct run --llm seeds`` asks the model once, before any input, and runs the seeds that pass
the checks after the user's own.

Each run's base URLs point at a stub on localhost, and neither real key reaches pyct, so no
request leaves the machine; the worker and the adapter run for real.
"""

import json
import time
from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct
from tests.acceptance.llm_stub import SEEDS_F, Stub, heads, llm_lines, llm_run

# `f(x: int)`: `if x == 1234:` guards `return 1`, and it calls `sign` in targets.llm.helpers
F = SEEDS_F
# `hang(x: int)`: never returns, so every run ends on its budget
HANG = "targets.isolate.hangs_with_finally::hang"


def replying(stub: Stub, *seeds: object) -> int:
    """The stub's port, once it replies with ``seeds``."""
    stub.reply = json.dumps(list(seeds))
    return stub.port


# llm-seeds-at-start-runs-after-the-user-s-seeds
def test_the_llm_s_seeds_run_after_the_user_s_before_any_solver_input(
    stub: Stub, tmp_path: Path
) -> None:
    result = llm_run(replying(stub, {"x": 1234}, {"x": 7}), tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert [(line["args"], line["source"]) for line in lines[:3]] == [
        ({"x": 0}, "seed"),
        ({"x": 1234}, "llm_seed"),
        ({"x": 7}, "llm_seed"),
    ]
    assert heads(result.stderr)[:3] == [
        'seed {"x": 0}',
        'llm seed 1 {"x": 1234}',
        'llm seed 2 {"x": 7}',
    ]


# llm-seeds-at-start-asks-once-before-any-input
def test_the_model_is_asked_once(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(replying(stub, {"x": 7}), tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0, result.stderr
    assert len(stub.received) == 1


# llm-seeds-at-start-sends-the-code-and-the-seeds
def test_the_request_holds_the_code_its_callee_the_signature_the_seed_and_the_goal(
    stub: Stub, tmp_path: Path
) -> None:
    llm_run(replying(stub, {"x": 7}), tmp_path, '{"x": 0}', "--llm", "seeds")

    [received] = stub.received
    sent = received.body["input"]
    assert isinstance(sent, list)
    [message] = sent
    text = message["content"]
    assert "def f(x: int):\n    if x == 1234:\n        return 1" in text
    assert "def sign(x: int) -> int:\n    if x < 0:" in text
    assert "\nSignature: (x: int)\n" in text
    assert '{"x": 0}' in text
    assert "coverage" in text


# llm-seeds-at-start-wait-is-not-budget-time
def test_the_wait_for_the_model_is_not_budget_time(stub: Stub, tmp_path: Path) -> None:
    stub.delay = 3
    replying(stub, {"x": 1})
    started = time.monotonic()

    result = llm_run(
        stub.port, tmp_path, '{"x": 0}', "--llm", "seeds", "--budget", "4", target=HANG
    )

    took = time.monotonic() - started
    assert "stopped: budget spent" in result.stderr
    # the 4 s budget and the 3 s wait; the upper bound only catches a run that overruns both
    assert 6.5 < took < 15, took


# llm-seed-dropped-fails-a-check
def test_a_seed_that_fails_a_check_is_dropped_with_the_check_s_reason(
    stub: Stub, tmp_path: Path
) -> None:
    result = llm_run(
        replying(stub, {"y": 1}, {"x": "a"}, {"x": 2}), tmp_path, '{"x": 0}', "--llm", "seeds"
    )

    plain_names = run_pyct(F, '{"y": 1}').stderr.strip()
    plain_types = run_pyct(F, '{"x": "a"}').stderr.strip()
    assert f"llm: dropped seed 1: {plain_names}" in result.stderr.splitlines()
    assert f"llm: dropped seed 2: {plain_types}" in result.stderr.splitlines()
    assert heads(result.stderr)[:2] == ['seed {"x": 0}', 'llm seed 3 {"x": 2}']
    sources = [line["source"] for line in input_lines(result.stdout)]
    assert sources.count("llm_seed") == 1


# llm-seed-dropped-repeats-a-seed
def test_a_seed_that_repeats_an_earlier_one_is_dropped(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(
        replying(stub, {"x": 0}, {"x": 5}, {"x": 5}), tmp_path, '{"x": 0}', "--llm", "seeds"
    )

    assert llm_lines(result.stderr)[1:-2] == [
        "llm: dropped seed 1: same seed as input 1",
        "llm: dropped seed 3: same seed as input 2",
    ]
    assert [line["args"] for line in input_lines(result.stdout)].count({"x": 5}) == 1


# llm-seed-dropped-past-the-fifth
def test_the_seeds_past_the_fifth_are_dropped(stub: Stub, tmp_path: Path) -> None:
    seeds = [{"x": n} for n in range(10, 17)]

    result = llm_run(replying(stub, *seeds), tmp_path, '{"x": 0}', "--llm", "seeds")

    assert llm_lines(result.stderr)[1:-2] == [
        "llm: dropped seed 6: more than 5 seeds",
        "llm: dropped seed 7: more than 5 seeds",
    ]
    lines = input_lines(result.stdout)
    assert [line["args"] for line in lines[1:6]] == seeds[:5]
    assert [line["source"] for line in lines[1:6]] == ["llm_seed"] * 5


# llm-switch-per-tool-all
def test_all_switches_on_every_tool_this_version_has(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(replying(stub, {"x": 7}), tmp_path, '{"x": 0}', "--llm", "all")

    assert llm_lines(result.stderr)[0] == "llm: openai:gpt-6-luna, tools: seeds, rewrites"


# llm-model-default
def test_the_default_model_is_openai_s_gpt_6_luna(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(replying(stub, {"x": 7}), tmp_path, '{"x": 0}', "--llm", "seeds")

    assert llm_lines(result.stderr)[0] == "llm: openai:gpt-6-luna, tools: seeds"
    [received] = stub.received
    assert (received.path, received.body["model"]) == ("/v1/responses", "gpt-6-luna")


# llm-model-chosen
def test_llm_model_picks_the_provider_s_adapter_and_the_model(stub: Stub, tmp_path: Path) -> None:
    model = "anthropic:claude-sonnet-5-5"

    result = llm_run(
        replying(stub, {"x": 1234}),
        tmp_path,
        '{"x": 0}',
        "--llm",
        "seeds",
        "--llm-model",
        model,
        key="ANTHROPIC_API_KEY",
    )

    assert llm_lines(result.stderr)[0] == "llm: anthropic:claude-sonnet-5-5, tools: seeds"
    [received] = stub.received
    assert (received.path, received.body["model"]) == ("/v1/messages", "claude-sonnet-5-5")
    assert input_lines(result.stdout)[1]["source"] == "llm_seed"
