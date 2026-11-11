"""Every ``pyct run --llm`` records its replies, and ``--llm-replay FILE`` answers each ask from a
recording by its tool, place and try, with no model called.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.cli import main
from tests.acceptance.harness import input_lines, let_pyct_run_in_process, run_pyct, summary_line
from tests.acceptance.llm_stub import (
    DUMMY_KEY,
    KEY_VARIABLES,
    Stub,
    closed_port,
    llm_env,
    read_recording,
    recordings,
    serving,
    write_recording,
)

# `f(x: int)`: `if x == 1234:` guards `return 1`, and it calls `sign` in targets.llm.helpers
F = "targets.llm.seeds::f"
# another function, `sign(x: int)`, which no recording of f's asks about
G = "targets.llm.helpers::sign"


@pytest.fixture
def stub() -> Iterator[Stub]:
    with serving(Stub()) as running:
        yield running


def llm_run(port: int, cache: Path, *argv: str, key: str | None = "OPENAI_API_KEY", target=F):
    return run_pyct(target, *argv, unset=KEY_VARIABLES, env=llm_env(cache, port, key))


def llm_lines(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith("llm: ")]


def sources(stdout: str) -> list[object]:
    return [line["source"] for line in input_lines(stdout)]


# llm-replies-recorded-one-line-per-reply
def test_a_run_records_each_reply_after_a_line_naming_the_model(stub: Stub, tmp_path: Path) -> None:
    stub.reply, stub.tokens = '[{"x": 1234}]', (1200, 300)

    result = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    assert result.returncode == 0, result.stderr
    [recording] = recordings(tmp_path)
    assert result.stderr.splitlines()[-1] == f"llm: replies recorded in {recording}"
    head, reply = read_recording(recording)
    assert (head["provider"], head["model"]) == ("openai", "gpt-6-luna")
    [received] = stub.received
    sent = received.body["input"]
    assert isinstance(sent, list)
    assert {key: reply[key] for key in ("tool", "place", "try", "request", "reply", "tokens")} == {
        "tool": "seeds",
        "place": F,
        "try": 1,
        "request": sent[0]["content"],
        "reply": '[{"x": 1234}]',
        "tokens": {"in": 1200, "out": 300},
    }


# llm-replies-recorded-every-run-asks-afresh
def test_each_run_asks_again_and_records_to_a_new_file(stub: Stub, tmp_path: Path) -> None:
    stub.reply = '[{"x": 7}]'

    llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")
    llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    assert len(stub.received) == 2
    first, second = recordings(tmp_path)
    assert first != second
    assert len(read_recording(first)) == len(read_recording(second)) == 2


# llm-replies-recorded-in-the-named-cache
def test_the_recording_is_under_the_named_cache_folder(stub: Stub, tmp_path: Path) -> None:
    cache = tmp_path / "named"

    result = llm_run(stub.port, cache, '{"x": 0}', "--llm", "seeds")

    [recording] = recordings(cache)
    assert recording.parent == cache / "llm" / "runs"
    assert f"llm: replies recorded in {recording}" in result.stderr.splitlines()


# llm-replies-recorded-holds-no-key
def test_the_recording_holds_the_reply_and_never_the_key(stub: Stub, tmp_path: Path) -> None:
    stub.reply = '[{"x": 1234}]'

    llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")

    [recording] = recordings(tmp_path)
    text = recording.read_text()
    assert read_recording(recording)[1]["reply"] == '[{"x": 1234}]'
    assert all(DUMMY_KEY not in line for line in text.splitlines())


# llm-run-replayed-calls-no-model
def test_a_replay_runs_the_recorded_seeds_with_no_model(stub: Stub, tmp_path: Path) -> None:
    stub.reply = '[{"x": 1234}, {"x": 7}]'
    recorded = llm_run(stub.port, tmp_path, '{"x": 0}', "--llm", "seeds")
    [recording] = recordings(tmp_path)

    replayed = llm_run(
        stub.port, tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording)
    )

    assert replayed.returncode == 0, replayed.stderr
    assert len(stub.received) == 1
    seeds = [line["args"] for line in input_lines(replayed.stdout) if line["source"] == "llm_seed"]
    assert seeds == [{"x": 1234}, {"x": 7}]
    summary = summary_line(replayed.stdout)
    assert summary["covered"] == summary_line(recorded.stdout)["covered"]
    llm = summary["llm"]
    assert isinstance(llm, dict)
    assert (llm["asks"], llm["replayed"], llm["tokens"]) == (0, 1, {"in": 0, "out": 0})


# llm-run-replayed-request-text-differs
def test_a_replay_answers_although_the_request_text_differs(tmp_path: Path) -> None:
    recording = write_recording(
        tmp_path / "old.jsonl", [{"request": "f as it was", "reply": '[{"y": 1}, {"x": 1234}]'}]
    )

    result = llm_run(
        closed_port(), tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording)
    )

    assert result.returncode == 0, result.stderr
    plain_names = run_pyct(F, '{"y": 1}').stderr.strip()
    assert f"llm: dropped seed 1: {plain_names}" in result.stderr.splitlines()
    assert [line["args"] for line in input_lines(result.stdout)][:2] == [{"x": 0}, {"x": 1234}]
    assert not any(line.startswith("llm: seeds ask skipped") for line in llm_lines(result.stderr))


# llm-run-replayed-other-place
def test_an_ask_the_recording_does_not_hold_is_skipped(stub: Stub, tmp_path: Path) -> None:
    recording = write_recording(tmp_path / "f.jsonl", [{"reply": '[{"x": 1234}]'}])

    result = llm_run(
        stub.port, tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording), target=G
    )

    assert result.returncode == 0, result.stderr
    assert "llm: seeds ask skipped: not in the replay file" in result.stderr.splitlines()
    assert stub.received == []
    assert "llm_seed" not in sources(result.stdout)


# llm-run-replayed-reports-the-recorded-model
def test_a_replay_reports_the_recorded_model(tmp_path: Path) -> None:
    recording = write_recording(
        tmp_path / "claude.jsonl", [{"reply": '[{"x": 7}]'}], model="anthropic:claude-sonnet-5-5"
    )

    result = llm_run(
        closed_port(), tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording)
    )

    assert llm_lines(result.stderr)[0] == "llm: anthropic:claude-sonnet-5-5, tools: seeds"
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert llm["model"] == "anthropic:claude-sonnet-5-5"


# llm-run-replayed-needs-no-key
def test_a_replay_needs_no_key_and_no_sdk(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    let_pyct_run_in_process(monkeypatch)
    for name, value in llm_env(tmp_path, closed_port(), key=None).items():
        monkeypatch.setenv(name, value)
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    found = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *rest: None if name == "openai" else found(name)
    )
    recording = write_recording(tmp_path / "f.jsonl", [{"reply": '[{"x": 1234}]'}])

    code = main(["run", F, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording)])

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert not any("running without the LLM" in line for line in captured.err.splitlines())
    assert [line["args"] for line in input_lines(captured.out)][:2] == [{"x": 0}, {"x": 1234}]
    assert sources(captured.out)[1] == "llm_seed"


def replay_refused(tmp_path: Path, recording: Path) -> tuple[int, str, str]:
    result = llm_run(
        closed_port(), tmp_path, '{"x": 0}', "--llm", "seeds", "--llm-replay", str(recording)
    )
    return result.returncode, result.stdout, result.stderr


# llm-run-replayed-unreadable-file
def test_a_replay_file_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    code, stdout, stderr = replay_refused(tmp_path, missing)

    assert (code, stdout) == (2, "")
    assert stderr.startswith(f"--llm-replay cannot read {missing}: ")


# llm-run-replayed-unreadable-file
def test_a_replay_file_whose_line_2_is_no_recorded_reply_is_refused(tmp_path: Path) -> None:
    recording = write_recording(tmp_path / "bad.jsonl", [{"reply": '[{"x": 7}]'}])
    head = recording.read_text().splitlines()[0]
    recording.write_text(f"{head}\n{json.dumps({'tool': 'seeds'})}\n")

    code, stdout, stderr = replay_refused(tmp_path, recording)

    assert (code, stdout) == (2, "")
    assert f"{recording}:2" in stderr


# llm-run-replayed-unreadable-file
def test_a_replay_file_holding_one_ask_twice_is_refused_naming_both_lines(tmp_path: Path) -> None:
    recording = write_recording(
        tmp_path / "twice.jsonl", [{"reply": '[{"x": 7}]'}, {"reply": '[{"x": 8}]'}]
    )

    code, stdout, stderr = replay_refused(tmp_path, recording)

    assert (code, stdout) == (2, "")
    assert f"{recording}:2" in stderr
    assert f"{recording}:3" in stderr
