"""Each run's recording: a new owner-only file under ``<cache>/llm/runs/``, one line per reply, or
a warning and no recording when the folder is not this user's alone."""

import errno
import json
import logging
import os
import stat
from pathlib import Path

import pytest

from pyct.config.llm import Model
from pyct.llm.recording import Recording
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply

MODEL = Model("openai", "gpt-6-luna")
SEEDS = Tool("seeds", 4000)


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "cache"
    monkeypatch.setenv("PYCT_CACHE_DIR", str(folder))
    return folder


def test_a_recording_starts_with_a_line_naming_the_model_and_the_tools(cache: Path) -> None:
    recording = Recording.start(MODEL, ("seeds",))

    assert recording.path is not None
    assert recording.path.parent == cache / "llm" / "runs"
    assert json.loads(recording.path.read_text()) == {
        "pyct_llm_recording": 1,
        "provider": "openai",
        "model": "gpt-6-luna",
        "tools": ["seeds"],
    }


def test_each_reply_is_one_line_after_the_first(cache: Path) -> None:
    recording = Recording.start(MODEL, ("seeds",))
    reply = Reply('[{"x": 1}]', AskCost(2, 1200, 300, 12.3456))

    recording.write(SEEDS, "m::f", "the request", reply)

    assert recording.path is not None
    _, line = recording.path.read_text().splitlines()
    assert json.loads(line) == {
        "tool": "seeds",
        "place": "m::f",
        "try": 2,
        "request": "the request",
        "reply": '[{"x": 1}]',
        "tokens": {"in": 1200, "out": 300},
        "seconds": 12.346,
    }


def test_the_folders_and_the_file_are_this_user_s_alone(cache: Path) -> None:
    recording = Recording.start(MODEL, ("seeds",))

    assert recording.path is not None
    for folder in (cache, cache / "llm", cache / "llm" / "runs"):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(recording.path.stat().st_mode) == 0o600


def test_a_folder_others_may_write_to_is_said_once_and_records_nothing(
    cache: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache.mkdir()
    cache.chmod(0o777)

    with caplog.at_level(logging.WARNING):
        recording = Recording.start(MODEL, ("seeds",))
        recording.write(SEEDS, "m::f", "text", Reply("[]", AskCost(1)))

    assert recording.path is None
    assert recording.failure == f"another user owns {cache} or may write to it"
    assert [record.getMessage() for record in caplog.records] == [
        f"llm: pyct cannot record the LLM's replies ({recording.failure})"
    ]
    assert not (cache / "llm").exists()


def test_a_write_that_fails_ends_the_recording_and_keeps_its_path_and_reason(
    cache: Path, caplog: pytest.LogCaptureFixture
) -> None:
    recording = Recording.start(MODEL, ("seeds",))
    assert recording.path is not None
    path = recording.path
    path.unlink()
    path.mkdir()

    with caplog.at_level(logging.WARNING):
        recording.write(SEEDS, "m::f", "text", Reply("[]", AskCost(1)))
        recording.write(SEEDS, "m::f", "text", Reply("[]", AskCost(2)))

    assert recording.path == path
    assert recording.failure == os.strerror(errno.EISDIR)
    assert len(caplog.records) == 1
