"""Each run's own recording of its replies, ``<cache>/llm/runs/<UTC time>-<8 hex>.jsonl``.

``<cache>`` is the folder the substituted code is kept in (``pyct.intercept.cache``). The folders
are made with mode 0700 and used only while they are this user's alone, as that cache's are, and
the file with mode 0600: a recording holds the target's code and the model's replies.

The first line names the recording: ``{"pyct_llm_recording": 1, "provider", "model", "tools"}``.
Each later line is one reply: ``tool``, ``place``, ``try``, ``request`` (the exact text the
tool asked with), ``reply``, ``tokens`` as ``{"in", "out"}``, and ``seconds``. A replayed
reply's tokens are the ones its own recording held. Each line is written and flushed as its
reply arrives, so a run that crashes keeps the replies it got. A failure is not recorded.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections.abc import Mapping
from pathlib import Path

from pyct.config.llm import Model
from pyct.intercept.cache import cache_folder, owned_alone
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Reply

logger = logging.getLogger(__name__)

# the version the first line names, so a later pyct can tell a recording it reads apart
VERSION = 1
# the key of the first line that holds the version, and that names the file a recording
HEAD_KEY = "pyct_llm_recording"


class Recording:
    """The run's recording: its path while it is written, or why no more replies are kept."""

    def __init__(self, path: Path | None, failure: str | None) -> None:
        self.path = path
        self.failure = failure

    @classmethod
    def start(cls, model: Model, tools: tuple[str, ...]) -> Recording:
        """A new file under ``<cache>/llm/runs/`` holding its first line. A folder that cannot be
        made or written, or is not this user's alone, is said once as a warning; the run goes on
        and records nothing."""
        head = {HEAD_KEY: VERSION, "provider": model.provider, "model": model.name}
        try:
            path = _new_file(_runs_folder())
            _append(path, {**head, "tools": list(tools)})
        except OSError as error:
            return cls._failed(error.strerror or type(error).__name__)
        except _NotOwnError as error:
            return cls._failed(str(error))
        return cls(path, None)

    @classmethod
    def _failed(cls, reason: str) -> Recording:
        logger.warning("llm: pyct cannot record the LLM's replies (%s)", reason)
        return cls(None, reason)

    def write(self, tool: Tool, place: str, text: str, reply: Reply) -> None:
        """One reply's line, appended and flushed. A write that fails is said once as a
        warning, and no later reply is kept."""
        if self.path is None:
            return
        cost = reply.cost
        line = {
            "tool": tool.name,
            "place": place,
            "try": cost.attempt,
            "request": text,
            "reply": reply.text,
            "tokens": {"in": cost.tokens_in, "out": cost.tokens_out},
            "seconds": round(cost.seconds, 3),
        }
        try:
            _append(self.path, line)
        except OSError as error:
            self.path = None
            self.failure = error.strerror or type(error).__name__
            logger.warning("llm: pyct cannot record the LLM's replies (%s)", self.failure)


class _NotOwnError(Exception):
    """A folder of the recording's path is another user's, or another user may write to it."""


def _runs_folder() -> Path:
    """``<cache>/llm/runs``, each folder made with mode 0700 and checked to be this user's alone."""
    folder = cache_folder()
    for each in (folder, folder / "llm", folder / "llm" / "runs"):
        each.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not owned_alone(each.stat()):
            raise _NotOwnError(f"another user owns {each} or may write to it")
    return folder / "llm" / "runs"


def _new_file(folder: Path) -> Path:
    """A file no run has made before, named for the UTC time and 8 random hex digits."""
    name = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}.jsonl"
    path = folder / name
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    return path


def _append(path: Path, line: Mapping[str, object]) -> None:
    """One JSON line at the file's end, opened for this line alone, so no input's process inherits
    a handle to it."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
        handle.flush()
