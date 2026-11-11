"""A stand-in for both providers' APIs on localhost, and the environment a ``pyct run`` with
``--llm`` gets in a test, so no test calls a model or sends anything off the machine.

``Stub`` answers OpenAI's Responses API and Anthropic's Messages API with the reply it is given,
after ``delay`` seconds, or with an HTTP error ``status``, and keeps each request it got.
``llm_env`` drops both real key variables, sets a dummy key, and points both SDKs' base URLs at
the stub, or at a local port nothing listens on.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# the real key variables, which no test passes on to pyct
KEY_VARIABLES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
# the dummy key a test gives pyct; a test that checks no output holds a key looks for this
DUMMY_KEY = "sk-pyct-test-dummy-key-0123456789"


@dataclass
class Received:
    """One request the stub got: its path and its JSON body."""

    path: str
    body: Mapping[str, object]


@dataclass
class Stub:
    """What the stub answers, and what it received."""

    reply: str = "[]"
    delay: float = 0.0
    status: int = 200
    # the reply's tokens in and out; None leaves the usage out of the reply
    tokens: tuple[int, int] | None = (120, 30)
    received: list[Received] = field(default_factory=list)
    port: int = 0

    @property
    def openai_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def anthropic_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def answer(self, path: str, body: Mapping[str, object]) -> tuple[int, Mapping[str, object]]:
        self.received.append(Received(path, body))
        time.sleep(self.delay)
        if self.status != 200:
            return self.status, {"error": {"message": "refused", "type": "error"}}
        if path.endswith("/responses"):
            return 200, _response(str(body["model"]), self.reply, self.tokens)
        return 200, _message(str(body["model"]), self.reply, self.tokens)


def _response(model: str, text: str, tokens: tuple[int, int] | None) -> Mapping[str, object]:
    """A Responses API reply holding ``text``."""
    content = [{"type": "output_text", "text": text, "annotations": []}]
    reply: dict[str, object] = {
        "id": "resp_stub",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_stub",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }
    if tokens is not None:
        reply["usage"] = {
            "input_tokens": tokens[0],
            "output_tokens": tokens[1],
            "total_tokens": sum(tokens),
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
    return reply


def _message(model: str, text: str, tokens: tuple[int, int] | None) -> Mapping[str, object]:
    """A Messages API reply holding ``text``. The Messages API always counts its tokens."""
    tokens = (0, 0) if tokens is None else tokens
    return {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    }


@contextlib.contextmanager
def serving(stub: Stub) -> Iterator[Stub]:
    """The stub, answering on a free localhost port until the block ends."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            status, reply = stub.answer(self.path, json.loads(self.rfile.read(length)))
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    stub.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()


def closed_port() -> int:
    """A localhost port nothing listens on: bound once, then let go."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def recordings(cache: Path) -> list[Path]:
    """The recordings runs made under the cache folder ``cache``, oldest name first."""
    folder = cache / "llm" / "runs"
    return sorted(folder.iterdir()) if folder.is_dir() else []


def read_recording(path: Path) -> list[dict[str, object]]:
    """Each line of a recording, read as JSON."""
    return [json.loads(line) for line in path.read_text().splitlines()]


def write_recording(
    path: Path, replies: list[Mapping[str, object]], model: str = "openai:gpt-6-luna"
) -> Path:
    """A recording as a run writes one: the first line naming ``model``, then one line per reply.
    Each reply's fields not given take a seeds ask's about ``targets.llm.seeds::f``, try 1."""
    provider, _, name = model.partition(":")
    head = {"pyct_llm_recording": 1, "provider": provider, "model": name, "tools": ["seeds"]}
    lines = [json.dumps(head)]
    for reply in replies:
        line = {
            "tool": "seeds",
            "place": "targets.llm.seeds::f",
            "try": 1,
            "request": "an earlier request",
            "reply": "[]",
            "tokens": {"in": 0, "out": 0},
            "seconds": 0.5,
            **reply,
        }
        lines.append(json.dumps(line))
    path.write_text("".join(f"{line}\n" for line in lines))
    return path


def llm_env(cache: Path, port: int, key: str | None = "OPENAI_API_KEY") -> dict[str, str]:
    """The variables a ``pyct run --llm`` test gives pyct: the dummy key under ``key`` (none when
    it is None), both base URLs at ``port`` on localhost, and the cache folder."""
    env = {
        "OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "PYCT_CACHE_DIR": str(cache),
    }
    if key is not None:
        env[key] = DUMMY_KEY
    return env
