"""The checks a seed passes before a run: its shape as JSON, its names, then its types.

Each refusal is a UsageError naming what is wrong, as the command line reports it.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping

from pyct.binding.annotations import contradictions
from pyct.binding.resolve import checked_annotations
from pyct.config.command_line import UsageError
from pyct.run.object_checks import ObjectCheck, fit_failure
from pyct.run.target import Target

# how many levels past the seed's own depth the check writes: room for the line, its forks, one
# fork, its condition, and a few operations the target applies to the value
LINE_NESTING = 8


def parse_seed(seed_text: str) -> Mapping[str, object]:
    """The seed is a JSON object, one key per parameter, nested no deeper than a line can hold."""
    try:
        seed = json.loads(seed_text)
    except json.JSONDecodeError as error:
        raise UsageError(f"args must be a JSON object: {error}") from error
    except RecursionError as error:
        raise UsageError("args nest too deep for Python to read") from error
    if not isinstance(seed, dict):
        raise UsageError(f"args must be a JSON object, got {type(seed).__name__}")
    _check_writable(seed)
    return seed


def _check_writable(seed: Mapping[str, object]) -> None:
    """Refuse a seed too deep for a line to hold a fork a few operations deep on its deepest value.

    The line holds each fork on a value inside the seed a few levels below
    the value, and Python's JSON writer stops at a depth of its own. So the
    check writes a list nested ``LINE_NESTING`` levels past the seed before
    any input runs, which allows for a few operations on the value.
    """
    depth = _depth(seed)
    probe: list[object] = [0]
    for _ in range(depth + LINE_NESTING - 1):
        probe = [probe]
    try:
        json.dumps(probe)
    except RecursionError as error:
        raise UsageError(
            f"args nest {depth} levels deep, too deep for pyct to write each input's line"
        ) from error


def _depth(value: object) -> int:
    """How many objects and arrays deep a JSON value nests, read in a loop, not a call per level."""
    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, level = pending.pop()
        if isinstance(item, dict):
            item = list(item.values())
        if isinstance(item, list):
            deepest = max(deepest, level)
            pending.extend((child, level + 1) for child in item)
    return deepest


def missing_args_message(signature: inspect.Signature) -> str:
    """Name the parameters the seed must give, and each way to pass it."""
    parameters = ", ".join(signature.parameters) or "no parameters"
    return (
        f"args are required: a JSON object for {parameters}\n"
        f"pass it after the target (pyct run MODULE::FUNCTION JSON) or through --args,"
        f" or a file of them through --seeds"
    )


def check_seed(target: Target, seed: Mapping[str, object]) -> None:
    """Refuse a seed with any of ``seed_refusals``' lines, every line at once."""
    refusals = seed_refusals(target, seed)
    if refusals:
        raise UsageError("\n".join(refusals))


def seed_refusals(target: Target, seed: Mapping[str, object]) -> list[str]:
    """Every reason to refuse a parsed seed: its names, then its types.

    When the seed's keys do not fit the parameters, that line is the only
    one. Otherwise, for a method whose instance each input builds, the lines
    for the object under its first parameter come first, checked against the
    constructor (``ObjectCheck``), then each other value that contradicts its
    annotation, in signature order.
    """
    fit = _fit_line(target.signature, seed)
    if fit is not None:
        return [fit]
    checks = checked_annotations(target.signature, target.fn)
    if target.self_class is None or target.self_name is None:
        return contradictions(checks, seed)
    name = target.self_name
    lines = ObjectCheck.of(target.self_class, target.constructor).lines(name, seed[name])
    others = {key: check for key, check in checks.items() if key != name}
    return lines + contradictions(others, seed)


def _fit_line(signature: inspect.Signature, seed: Mapping[str, object]) -> str | None:
    """Why the seed's keys do not fit the parameters, or None when they fit. Names only, not
    types.

    A positional-only parameter is named too, and bound by position, as the
    call will pass it.
    """
    reason = fit_failure(signature, seed)
    if reason is None:
        return None
    # bind names a missing parameter before an unexpected key, so name the keys too
    given = ", ".join(seed) or "nothing"
    parameters = ", ".join(signature.parameters) or "no parameters"
    return f"args ({given}) do not fit ({parameters}): {reason}"
