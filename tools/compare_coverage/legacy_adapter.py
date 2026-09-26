"""Run legacy's engine on one target and print one JSON line. Legacy's interpreter runs this file.

The checker starts it as ``DIR/.venv/bin/python -P legacy_adapter.py REQUEST`` in the entry's
root. REQUEST is ``{"target", "seed", "root", "limits": {"budget", "plateau",
"solver_timeout"}}``; the one line back is ``{"file", "covered", "stopped", "inputs",
"failure"}``. Only JSON crosses between the two environments (decision
legacy-oracle-through-one-adapter). This is the only code that knows legacy, and it is new
code against main's public API; it copies none of legacy's.

- It imports the standard library and legacy's engine only. It runs in legacy's environment,
  where no v2 module exists, and ``-P`` keeps this file's folder off ``sys.path``, so no v2
  module can shadow a legacy one.
- The engine import is dynamic: the name ``pyct`` means legacy's package only at run time, in
  legacy's interpreter, and a static import would be read by every tool as v2's.
- ``ExecutionConfig``: ``timeout_seconds`` and ``seed_soft_timeout`` are the budget, so the
  budget bounds the seed too, as it does in v2. ``max_iterations`` is ``sys.maxsize``, which
  lifts legacy's cap of 50 inputs. ``plateau_threshold`` is the plateau. ``solver_timeout`` is
  the whole seconds the checker rounded up, as legacy takes whole seconds. ``scope`` is the
  target's whole file, so legacy's plateau counts a new line anywhere in it, as v2's does.
- Legacy runs isolated, its default and how its benchmark ran it: a spawned child imports the
  target again, and a watchdog returns what a hung child covered. The ``__main__`` guard is
  what lets that child import this file.
- Stdout points at stderr while legacy runs, so nothing legacy, the target or cvc5 prints can
  reach it. The one line is written once it is put back.
"""

import contextlib
import importlib
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Engine:
    """What the adapter takes from legacy's engine: its runner, config and scope types."""

    run_concolic: Callable[..., Any]
    config: Callable[..., Any]
    scope: Any


def load_engine() -> Engine:
    """Legacy's engine, imported before the entry's root goes on the path so nothing shadows it."""
    engine = importlib.import_module("pyct")
    coverage_scope = importlib.import_module("pyct.engine.coverage_scope")
    return Engine(
        run_concolic=engine.run_concolic,
        config=engine.ExecutionConfig,
        scope=coverage_scope.CoverageScope,
    )


def main(argv: list[str], load: Callable[[], Engine] = load_engine) -> int:
    """Run the request in ``argv[1]`` with stdout pointed at stderr, then print the one line.

    Both the file descriptor and ``sys.stdout`` point at stderr: a child process writes to
    the descriptor, and Python code writes to whatever ``sys.stdout`` is bound to.
    """
    request = json.loads(argv[1])
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            line = report(request, load())
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
    print(json.dumps(line), flush=True)
    return 0


def report(request: Mapping[str, Any], engine: Engine) -> dict[str, Any]:
    """Legacy's run of the request, as the one line the checker reads."""
    try:
        target, file = _target(request["target"], request["root"])
    except Exception as error:
        failure = f"cannot import {request['target']}: {error!r}"
        return {"file": None, "covered": [], "stopped": None, "inputs": None, "failure": failure}
    config = _config(engine, request["limits"], file)
    result = engine.run_concolic(target, dict(request["seed"]), config=config, plugins=None)
    return {
        "file": file,
        "covered": sorted(result.executed_lines),
        "stopped": result.termination_reason,
        "inputs": result.iterations,
        "failure": None if result.success else f"{result.termination_reason}: {_error(result)}",
    }


def _error(result: Any) -> str:
    """Legacy's own words for a failed run: its error, else the last input's, else what it is.

    When legacy's watchdog stops a hung child, it returns the child's last checkpoint with no
    error, and the stopped input, last among the inputs, carries the text.
    """
    if result.error is not None:
        return result.error
    errors = [record.error for record in result.inputs_generated if record.error is not None]
    return errors[-1] if errors else "legacy gave a partial result and no error"


def _target(spec: str, root: str) -> tuple[Any, str]:
    """``MODULE::NAME`` imported with ``root`` first on the path, and the file it came from."""
    module_name, name = spec.split("::")
    sys.path.insert(0, root)
    module = importlib.import_module(module_name)
    file = getattr(module, "__file__", None)
    if not file:
        raise ImportError(f"{module_name} has no source file")
    return getattr(module, name), file


def _config(engine: Engine, limits: Mapping[str, Any], file: str) -> Any:
    """Legacy's ``ExecutionConfig`` for the limits, as the module docstring sets each field."""
    return engine.config(
        timeout_seconds=limits["budget"],
        seed_soft_timeout=limits["budget"],
        max_iterations=sys.maxsize,
        plateau_threshold=limits["plateau"],
        solver_timeout=limits["solver_timeout"],
        scope=engine.scope.for_paths([file]),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
