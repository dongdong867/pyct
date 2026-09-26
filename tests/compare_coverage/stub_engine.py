"""A stand-in for legacy's engine, for tests: legacy's public names, answers from a script.

``stub_checkout`` in ``conftest.py`` copies this file to ``src/pyct/__init__.py`` in a folder
laid out like a legacy checkout, so the real adapter runs against it in a real process. It
holds no legacy code: only the names and fields the adapter uses (``run_concolic``,
``ExecutionConfig``, ``CoverageScope``). Its answers come from ``stub.json`` in the checkout,
keyed by ``MODULE::NAME``:

- ``lines``: the lines to report; without it, the lines of the target's file that the seed ran
- ``stopped``, ``inputs``, ``success``, ``error``: the result's other fields
- ``sleep``: seconds to sleep first, for a side that runs too long
- ``exit``: end the process at once with this code, after printing ``say`` to stderr

Each call's config and process id are appended to ``calls.jsonl`` in the checkout.
"""

import dataclasses
import json
import os
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

CHECKOUT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CoverageScope:
    files: frozenset[str]

    @classmethod
    def for_paths(cls, paths: Iterable[str]) -> "CoverageScope":
        return cls(files=frozenset(paths))


@dataclass(frozen=True)
class ExecutionConfig:
    timeout_seconds: float
    max_iterations: int
    solver_timeout: int
    plateau_threshold: int
    seed_soft_timeout: float
    scope: CoverageScope


@dataclass(frozen=True)
class Result:
    success: bool
    executed_lines: frozenset[int]
    iterations: int
    termination_reason: str
    error: str | None
    inputs_generated: tuple[Any, ...] = ()


def run_concolic(
    target: Callable[..., Any],
    initial_args: dict[str, Any],
    *,
    config: ExecutionConfig,
    plugins: list[Any] | None = None,
) -> Result:
    script = _script(f"{target.__module__}::{target.__name__}")
    _record(config, plugins)
    time.sleep(script.get("sleep", 0))
    if "exit" in script:
        print(script.get("say", ""), file=sys.stderr, flush=True)
        os._exit(script["exit"])
    lines = script["lines"] if "lines" in script else _run_once(target, initial_args, config)
    return Result(
        success=script.get("success", True),
        executed_lines=frozenset(lines),
        iterations=script.get("inputs", 1),
        termination_reason=script.get("stopped", "exhausted"),
        error=script.get("error"),
    )


def _script(target: str) -> dict[str, Any]:
    path = CHECKOUT / "stub.json"
    return json.loads(path.read_text()).get(target, {}) if path.exists() else {}


def _record(config: ExecutionConfig, plugins: list[Any] | None) -> None:
    fields = {**dataclasses.asdict(config), "scope": sorted(config.scope.files)}
    with open(CHECKOUT / "calls.jsonl", "a") as calls:
        calls.write(json.dumps({"config": fields, "plugins": plugins, "pid": os.getpid()}) + "\n")


def _run_once(
    target: Callable[..., Any], args: dict[str, Any], config: ExecutionConfig
) -> set[int]:
    lines: set[int] = set()

    def trace(frame: FrameType, event: str, _arg: object) -> Callable[..., Any]:
        if event == "line" and frame.f_code.co_filename in config.scope.files:
            lines.add(frame.f_lineno)
        return trace

    sys.settrace(trace)
    try:
        target(**args)
    except Exception:
        pass
    finally:
        sys.settrace(None)
    return lines
