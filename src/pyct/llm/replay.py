"""``--llm-replay FILE``: a recording read and checked before the run, and the caller that
answers each ask from it by tool, place and try, calling no model.

The request text is never compared: a request can quote past runs, which differ between runs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyct.config.command_line import UsageError
from pyct.config.llm import PROVIDERS, Model
from pyct.llm.recording import HEAD_KEY, VERSION
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why

# why an ask a replay's file holds no reply for is skipped
NOT_IN_THE_FILE = "not in the replay file"

# one recorded reply's key: its tool, place and try
type Key = tuple[str, str, int]


@dataclass(frozen=True)
class Recorded:
    """One recorded reply, with the tokens the model spent on it then."""

    text: str
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class Replay:
    """A recording as read: the model it names, and each reply by its tool, place and try."""

    model: Model
    replies: Mapping[Key, Recorded]


def read_replay(path: Path) -> Replay:
    """The recording at ``path``, or a UsageError naming the file and the line or lines at fault:
    a file that cannot be read, a first line that names no provider and model, a later line
    that is not a recorded reply, or two lines that hold the same tool, place and try."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        reason = getattr(error, "strerror", None) or type(error).__name__
        raise UsageError(f"--llm-replay cannot read {path}: {reason}") from error
    model = _model(_json(lines[0]) if lines else None)
    if model is None:
        raise UsageError(f"--llm-replay: {path}:1 does not name a recording's provider and model")
    replies: dict[Key, Recorded] = {}
    first_line: dict[Key, int] = {}
    for number, text in enumerate(lines[1:], start=2):
        read = _reply(_json(text))
        if read is None:
            raise UsageError(f"--llm-replay: {path}:{number} is not a recorded reply")
        key, recorded = read
        if key in first_line:
            raise UsageError(
                f"--llm-replay: {path}:{first_line[key]} and {path}:{number} hold the same tool,"
                " place and try"
            )
        first_line[key], replies[key] = number, recorded
    return Replay(model, replies)


def _json(text: str) -> object:
    """The line's JSON value, or None when it is not JSON."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        return None


def _model(head: object) -> Model | None:
    """The model a first line names, or None when it is no recording's first line."""
    if not isinstance(head, dict) or head.get(HEAD_KEY) != VERSION:
        return None
    provider, name = head.get("provider"), head.get("model")
    if provider not in PROVIDERS or not isinstance(name, str) or not name:
        return None
    return Model(str(provider), name)


def _reply(line: object) -> tuple[Key, Recorded] | None:
    """A reply line's key and reply, or None when it lacks a field or one has the wrong type."""
    if not isinstance(line, dict):
        return None
    match line:
        case {
            "tool": str(tool),
            "place": str(place),
            "try": int(attempt),
            "request": str(),
            "reply": str(reply),
            "tokens": {"in": int(tokens_in), "out": int(tokens_out)},
            "seconds": int() | float() as seconds,
        } if _counts((attempt, 1), (tokens_in, 0), (tokens_out, 0)) and not isinstance(
            seconds, bool
        ):
            return (tool, place, attempt), Recorded(reply, tokens_in, tokens_out)
        case _:
            return None


def _counts(*pairs: tuple[int, int]) -> bool:
    """Whether each value is a whole number of at least its least; JSON's true and false are
    not."""
    return all(not isinstance(value, bool) and value >= least for value, least in pairs)


@dataclass(frozen=True)
class ReplayCaller:
    """A ``Caller`` that answers each ask with the recorded reply of the same tool, place and
    try, and skips one the recording does not hold. It calls no model and needs no key."""

    replay: Replay

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        started = time.monotonic()
        recorded = self.replay.replies.get((tool.name, place, attempt))
        seconds = time.monotonic() - started
        if recorded is None:
            return Unanswered(Why.NOT_RECORDED, NOT_IN_THE_FILE, AskCost(attempt, seconds=seconds))
        cost = AskCost(attempt, recorded.tokens_in, recorded.tokens_out, seconds, replayed=True)
        return Reply(recorded.text, cost)
