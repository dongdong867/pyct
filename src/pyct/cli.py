"""Command-line interface for PyCT."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable
from typing import Any

from pyct import run_concolic
from pyct.config.execution import ExecutionConfig


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help()
        return 2

    try:
        initial_args = _parse_json_args(args.args)
    except _ArgsParseError as e:
        print(f"error: invalid --args JSON: {e}", file=sys.stderr)
        return 1

    try:
        target = _resolve_target(args.target)
    except _TargetResolutionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    config = ExecutionConfig(max_iterations=args.max_iterations)
    result = run_concolic(
        target=target,
        initial_args=initial_args,
        config=config,
        isolated=not args.no_isolated,
    )
    _print_summary(result, args.target)
    return 0 if result.success else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyct", description="Python concolic testing")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Run concolic exploration on a target")
    run.add_argument(
        "target",
        help="Target in the form 'module.path::function_name'",
    )
    run.add_argument(
        "--args",
        default="{}",
        help="JSON dict of initial argument values (default: '{}')",
    )
    run.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximum exploration iterations (default: 50)",
    )
    run.add_argument(
        "--no-isolated",
        action="store_true",
        help="Run in-process instead of an isolated subprocess "
        "(faster, but unsafe for targets that may crash native code)",
    )
    return parser


class _ArgsParseError(Exception):
    """Raised when --args cannot be parsed as a JSON object."""


class _TargetResolutionError(Exception):
    """Raised when the target spec cannot be resolved to a callable."""


def _parse_json_args(raw: str) -> dict[str, Any]:
    """Parse the --args value into a dict, with friendly errors."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise _ArgsParseError(str(e)) from e

    if not isinstance(parsed, dict):
        raise _ArgsParseError("--args must be a JSON object (dict)")
    return parsed


def _resolve_target(spec: str) -> Callable:
    """Resolve ``module.path::function_name`` to a callable."""
    if "::" not in spec:
        raise _TargetResolutionError(f"target '{spec}' is not in 'module.path::function_name' form")

    module_path, func_name = spec.split("::", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise _TargetResolutionError(f"could not import module '{module_path}': {e}") from e

    target: Any = module
    for attr in func_name.split("."):
        try:
            target = getattr(target, attr)
        except AttributeError as e:
            raise _TargetResolutionError(
                f"function '{func_name}' not found in module '{module_path}'"
            ) from e

    if not callable(target):
        raise _TargetResolutionError(f"'{spec}' is not callable")
    return target


def _print_summary(result: Any, target_spec: str) -> None:
    """Print a short human-readable summary of the run."""
    status = "success" if result.success else "failure"
    print(f"pyct: {status} on {target_spec}")
    print(f"  coverage: {result.coverage_percent:.1f}%")
    print(f"  paths_explored: {result.paths_explored}")
    print(f"  iterations: {result.iterations}")
    print(f"  termination: {result.termination_reason}")
    if result.error:
        print(f"  error: {result.error}")
