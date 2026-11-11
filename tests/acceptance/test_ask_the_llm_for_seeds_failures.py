"""An LLM problem never stops a run that has a seed of its own, and a run with none stops only
when the LLM gives no usable seed.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

import importlib.util
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.cli import main
from tests.acceptance.harness import input_lines, let_pyct_run_in_process, run_pyct
from tests.acceptance.llm_stub import DUMMY_KEY, KEY_VARIABLES, Stub, closed_port, llm_env, serving

# `f(x: int)`: `if x == 1234:` guards `return 1`, and it calls `sign` in targets.llm.helpers
F = "targets.llm.seeds::f"
# the longest a run waiting out the 30 s ask may take, its own short run included
SLOW_RUN = 55


@pytest.fixture
def stub() -> Iterator[Stub]:
    with serving(Stub()) as running:
        yield running


def llm_run(port: int, cache: Path, *argv: str, key: str | None = "OPENAI_API_KEY", timeout=30):
    env = llm_env(cache, port, key)
    return run_pyct(F, *argv, unset=KEY_VARIABLES, env=env, timeout=timeout)


def sources(stdout: str) -> list[object]:
    return [line["source"] for line in input_lines(stdout)]


# llm-failure-never-stops-a-run-no-package
def test_a_missing_sdk_is_said_once_and_the_run_is_plain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    let_pyct_run_in_process(monkeypatch)
    for name, value in llm_env(tmp_path, closed_port()).items():
        monkeypatch.setenv(name, value)
    found = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *rest: None if name == "openai" else found(name)
    )

    code = main(["run", F, '{"x": 0}', "--llm", "seeds"])

    captured = capsys.readouterr()
    said = (
        "llm: the openai package is not installed (pip install 'pyct[openai]');"
        " running without the LLM"
    )
    assert code == 0
    assert captured.err.splitlines().count(said) == 1
    assert [line for line in captured.err.splitlines() if line.startswith("llm: ")] == [said]
    assert "llm_seed" not in sources(captured.out)
    assert sources(captured.out)[0] == "seed"


# llm-failure-never-stops-a-run-no-key
def test_a_missing_key_is_said_once_and_the_run_is_plain(stub: Stub, tmp_path: Path) -> None:
    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds", key=None)

    assert result.returncode == 0
    llm = [line for line in result.stderr.splitlines() if line.startswith("llm: ")]
    assert llm == ["llm: no OPENAI_API_KEY; running without the LLM"]
    assert sources(result.stdout)[:2] == ["seed", "solver"]
    assert stub.received == []


# llm-failure-never-stops-a-run-down
def test_a_provider_that_cannot_be_reached_is_skipped(tmp_path: Path) -> None:
    result = llm_run(closed_port(), tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0
    assert "llm: seeds ask skipped: APIConnectionError" in result.stderr.splitlines()
    assert sources(result.stdout)[:2] == ["seed", "solver"]


# llm-failure-never-stops-a-run-slow
def test_an_ask_with_no_reply_in_30_s_is_skipped(stub: Stub, tmp_path: Path) -> None:
    stub.delay = 40
    started = time.monotonic()

    result = llm_run(
        stub.port, tmp_path, '{"x": 0}', "--llm", "seeds", "--budget", "none", timeout=SLOW_RUN
    )

    assert 30 <= time.monotonic() - started < SLOW_RUN
    assert result.returncode == 0
    assert "llm: seeds ask skipped: no reply in 30 s" in result.stderr.splitlines()
    assert sources(result.stdout)[:2] == ["seed", "solver"]


# llm-failure-never-stops-a-run-wrong-form
def test_a_reply_with_no_json_array_is_ignored(stub: Stub, tmp_path: Path) -> None:
    stub.reply = "x should be 1234"

    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0
    assert "llm: seeds reply ignored: no JSON array in the reply" in result.stderr.splitlines()
    assert sources(result.stdout)[:2] == ["seed", "solver"]


# llm-failure-never-stops-a-run-key-not-printed
def test_a_refused_key_is_skipped_and_its_value_never_printed(stub: Stub, tmp_path: Path) -> None:
    stub.status = 401

    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    assert "llm: seeds ask skipped: AuthenticationError (401)" in result.stderr.splitlines()
    assert DUMMY_KEY not in result.stdout
    assert DUMMY_KEY not in result.stderr
    assert sources(result.stdout)[:2] == ["seed", "solver"]


# llm-seeds-no-seed-refused-none-pass
def test_a_run_with_no_seed_whose_llm_seeds_all_fail_is_refused(stub: Stub, tmp_path: Path) -> None:
    stub.reply = '[{"y": 1}]'

    result = llm_run(stub.port, tmp_path, "--llm", "seeds")

    lines = result.stderr.splitlines()
    assert lines[-2].startswith("llm: dropped seed 1: args (y) do not fit (x)")
    assert lines[-1] == "no seed: the LLM gave none (every seed was dropped)"
    assert result.returncode == 1
    assert result.stdout == ""


# llm-seeds-no-seed-refused-no-key
def test_a_run_with_no_seed_and_no_key_is_refused_without_an_ask(
    stub: Stub, tmp_path: Path
) -> None:
    result = llm_run(stub.port, tmp_path, "--llm", "seeds", key=None)

    assert result.stderr.splitlines() == ["no seed: the LLM gave none (no OPENAI_API_KEY)"]
    assert result.returncode == 1
    assert result.stdout == ""
    assert stub.received == []


# llm-seeds-no-seed-refused-skipped
def test_a_run_with_no_seed_whose_ask_gets_no_reply_is_refused(stub: Stub, tmp_path: Path) -> None:
    stub.delay = 40

    result = llm_run(stub.port, tmp_path, "--llm", "seeds", "--budget", "none", timeout=SLOW_RUN)

    assert result.stderr.splitlines()[-1] == "no seed: the LLM gave none (no reply in 30 s)"
    assert result.returncode == 1
    assert result.stdout == ""


def test_a_run_with_no_seed_and_no_llm_names_llm_seeds_as_a_way_to_start() -> None:
    result = run_pyct(F)

    assert result.returncode == 2
    assert "--llm seeds" in result.stderr


def test_the_llm_s_line_follows_the_skipped_seeds(stub: Stub, tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text('{"x": 0}\n{"x": 0}\n')

    result = llm_run(stub.port, tmp_path, "--seeds", str(seeds), "--llm", "seeds", key=None)

    assert result.stderr.splitlines()[:2] == [
        f"skipped {seeds}:2, same seed as line 1",
        "llm: no OPENAI_API_KEY; running without the LLM",
    ]
