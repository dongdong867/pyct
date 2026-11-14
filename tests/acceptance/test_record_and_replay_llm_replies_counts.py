"""The summary line's ``llm`` entry and stderr's closing ``llm:`` lines count each ask, and
``--llm-limit`` takes a positive number of tokens.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

import pytest

from tests.acceptance.harness import run_pyct, summary_line
from tests.acceptance.llm_stub import (
    KEY_VARIABLES,
    SEEDS_F,
    Stub,
    closed_port,
    llm_env,
    llm_run,
    write_recording,
)

# `f(x: int)`: `if x == 1234:` guards `return 1`
F = SEEDS_F


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
        "summaries": [],
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


# llm-token-limit-no-more-asks, llm-token-limit-replay-stops-where-the-recording-did: the
# command line's half, the limit line once and no tokens spent. The seeds tool asks once per run,
# so the refused second ask is tested through Connection in tests/unit/llm/test_connection.py
def test_a_replay_whose_reply_reaches_the_limit_says_so_once_and_spends_nothing(
    tmp_path: Path,
) -> None:
    recording = write_recording(
        tmp_path / "r.jsonl", [{"reply": '[{"x": 7}]', "tokens": {"in": 1200, "out": 300}}]
    )

    result = llm_run(
        closed_port(),
        tmp_path,
        '{"x": 0}',
        "--llm",
        "seeds",
        "--llm-replay",
        str(recording),
        "--llm-limit",
        "1000",
    )

    assert result.returncode == 0, result.stderr
    said = "llm: token limit reached; no more asks"
    assert result.stderr.splitlines().count(said) == 1
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert (llm["replayed"], llm["tokens"]) == (1, {"in": 0, "out": 0})
