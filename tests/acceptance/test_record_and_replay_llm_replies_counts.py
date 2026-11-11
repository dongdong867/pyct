"""The summary line's ``llm`` entry and stderr's closing ``llm:`` lines count each ask, and
``--llm-limit`` takes a positive number of tokens.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.acceptance.harness import run_pyct, summary_line
from tests.acceptance.llm_stub import KEY_VARIABLES, Stub, closed_port, llm_env, serving

# `f(x: int)`: `if x == 1234:` guards `return 1`
F = "targets.llm.seeds::f"


@pytest.fixture
def stub() -> Iterator[Stub]:
    with serving(Stub()) as running:
        yield running


def llm_run(port: int, cache: Path, *argv: str):
    return run_pyct(F, *argv, unset=KEY_VARIABLES, env=llm_env(cache, port))


# llm-tokens-reported-summary-and-stderr
def test_the_summary_and_stderr_count_the_ask_its_tokens_and_its_wait(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply, stub.tokens = '[{"x": 1234}]', (1200, 300)

    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0, result.stderr
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    seconds = llm.pop("seconds")
    assert isinstance(seconds, float) and 0 < seconds < 30
    assert llm == {
        "model": "openai:gpt-6-luna",
        "tools": ["seeds"],
        "asks": 1,
        "replayed": 0,
        "skipped": 0,
        "tokens": {"in": 1200, "out": 300},
    }
    counts = "llm: 1 asks, 0 replayed, 0 skipped, 1200 tokens in, 300 out"
    assert result.stderr.splitlines()[-2] == f"{counts}, {seconds:.1f} s waiting"
    assert result.stderr.splitlines()[-1].startswith("llm: replies recorded in ")


# llm-switch-per-tool-off
def test_a_run_with_no_llm_writes_null_says_nothing_and_records_nothing(tmp_path: Path) -> None:
    result = run_pyct(F, '{"x": 0}', unset=KEY_VARIABLES, env=llm_env(tmp_path, closed_port()))

    assert result.returncode == 0, result.stderr
    assert summary_line(result.stdout)["llm"] is None
    assert not any(line.startswith("llm:") for line in result.stderr.splitlines())
    assert not (tmp_path / "llm").exists()


# llm-token-limit-refused-value
@pytest.mark.parametrize("limit", ["0", "many", "-5"])
def test_a_limit_that_is_not_a_positive_number_of_tokens_is_refused(
    tmp_path: Path, limit: str
) -> None:
    result = llm_run(closed_port(), tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-limit", limit)

    assert (result.returncode, result.stdout) == (2, "")
    assert result.stderr.startswith("--llm-limit takes a positive number of tokens")
