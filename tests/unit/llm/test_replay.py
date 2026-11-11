"""A recording read for ``--llm-replay``, and the caller that answers from it by tool, place and
try."""

import json
from pathlib import Path

import pytest

from pyct.config.command_line import UsageError
from pyct.config.llm import Model
from pyct.llm.connection import Connection
from pyct.llm.replay import Recorded, ReplayCaller, read_replay
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Reply, Unanswered, Why
from tests.acceptance.llm_stub import NO_RECORDING, write_recording

SEEDS = Tool("seeds", 4000)


# llm-run-replayed-later-try
def test_each_try_gets_its_recorded_reply_and_a_later_one_is_skipped(tmp_path: Path) -> None:
    recording = write_recording(
        tmp_path / "two.jsonl",
        [{"place": "m::f", "try": 1, "reply": "one"}, {"place": "m::f", "try": 2, "reply": "two"}],
    )
    connection = Connection(ReplayCaller(read_replay(recording)), NO_RECORDING)

    answers = [connection.ask(SEEDS, "m::f", "asked again") for _ in range(3)]

    first, second, third = answers
    assert isinstance(first, Reply) and isinstance(second, Reply)
    assert (first.text, second.text) == ("one", "two")
    assert isinstance(third, Unanswered)
    assert (third.why, third.reason) == (Why.NOT_RECORDED, "not in the replay file")


def test_a_replayed_reply_reaches_its_tool_with_no_tokens_spent(tmp_path: Path) -> None:
    recording = write_recording(tmp_path / "r.jsonl", [{"tokens": {"in": 1200, "out": 300}}])
    replay = read_replay(recording)

    answer = Connection(ReplayCaller(replay), NO_RECORDING).ask(
        SEEDS, "targets.llm.seeds::f", "text"
    )

    assert replay.replies[("seeds", "targets.llm.seeds::f", 1)] == Recorded("[]", 1200, 300)
    assert isinstance(answer, Reply)
    assert (answer.cost.tokens_in, answer.cost.tokens_out, answer.cost.replayed) == (0, 0, True)


def test_the_recording_names_the_replay_s_model(tmp_path: Path) -> None:
    recording = write_recording(tmp_path / "r.jsonl", [], model="anthropic:claude-haiku-5-5")

    assert read_replay(recording).model == Model("anthropic", "claude-haiku-5-5")


def refusal(path: Path) -> str:
    with pytest.raises(UsageError) as refused:
        read_replay(path)
    return str(refused.value)


@pytest.mark.parametrize(
    "head",
    [
        "",
        "not json",
        json.dumps({"provider": "openai", "model": "gpt-6-luna"}),
        json.dumps({"pyct_llm_recording": 1, "provider": "gemini", "model": "pro"}),
        json.dumps({"pyct_llm_recording": 1, "provider": "openai", "model": ""}),
    ],
)
def test_a_first_line_that_names_no_recording_s_model_is_refused(tmp_path: Path, head: str) -> None:
    path = tmp_path / "head.jsonl"
    path.write_text(f"{head}\n")

    assert refusal(path) == (
        f"--llm-replay: {path}:1 does not name a recording's provider and model"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"try": 0},
        {"try": True},
        {"try": "1"},
        {"tool": None},
        {"request": 3},
        {"tokens": {"in": -1, "out": 0}},
        {"tokens": {"in": 1}},
        {"seconds": "0.5"},
        {"seconds": False},
    ],
)
def test_a_line_that_is_not_a_recorded_reply_is_refused_by_its_number(
    tmp_path: Path, change: dict[str, object]
) -> None:
    path = write_recording(tmp_path / "bad.jsonl", [{}, change])

    assert refusal(path) == f"--llm-replay: {path}:3 is not a recorded reply"


def test_a_line_that_is_not_json_is_refused_by_its_number(tmp_path: Path) -> None:
    path = write_recording(tmp_path / "bad.jsonl", [{}])
    path.write_text(path.read_text() + "[\n")

    assert refusal(path) == f"--llm-replay: {path}:3 is not a recorded reply"


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bytes.jsonl"
    path.write_bytes(b"\xff\xfe\x00")

    assert refusal(path) == f"--llm-replay cannot read {path}: UnicodeDecodeError"


def test_the_same_try_on_two_lines_is_refused_naming_both(tmp_path: Path) -> None:
    path = write_recording(tmp_path / "twice.jsonl", [{}, {"place": "m::g"}, {}])

    assert refusal(path) == (
        f"--llm-replay: {path}:2 and {path}:4 hold the same tool, place and try"
    )


def test_a_line_with_a_number_too_long_to_read_is_refused_by_its_number(tmp_path: Path) -> None:
    path = write_recording(tmp_path / "long.jsonl", [{}])
    path.write_text(path.read_text() + '{"try": ' + "9" * 5000 + "}\n")

    assert refusal(path) == f"--llm-replay: {path}:3 is not a recorded reply"


@pytest.mark.parametrize("version", ["true", "1.0"])
def test_a_first_line_whose_version_is_not_the_number_1_is_refused(
    tmp_path: Path, version: str
) -> None:
    path = tmp_path / "head.jsonl"
    path.write_text(f'{{"pyct_llm_recording": {version}, "provider": "openai", "model": "m"}}\n')

    assert refusal(path) == (
        f"--llm-replay: {path}:1 does not name a recording's provider and model"
    )
