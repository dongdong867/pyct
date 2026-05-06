"""Type aliases and data structures for engine values.

This module is a leaf — it imports nothing from the rest of the engine and
hosts the value types that engine state, results, and plugin events share.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

Seed = dict[str, Any]
"""A seed input: maps parameter name to concrete value."""

Constraint = Any
"""Path constraint recorded during concolic execution.

TODO(v2): Replace this alias with a proper frozen dataclass that
wraps the symbolic expression and the branch decision it represents.
Kept as Any for v1 to avoid constraining the solver integration work.
"""

Resolution = dict[str, Any]
"""A plugin's response to on_constraint_unknown: maps parameter name to value.

Same shape as Seed, but distinguished in code to signal intent.
"""


class Provenance(StrEnum):
    """Source of an input the engine produced and executed.

    Values are event-keyed rather than plugin-keyed so multiple plugins
    contributing to the same dispatcher event share a label.
    """

    SEED = "seed"
    SOLVER = "solver"
    PLUGIN_SEED = "plugin_seed"
    PLUGIN_PLATEAU = "plugin_plateau"
    PLUGIN_UNKNOWN = "plugin_unknown"


class Outcome(StrEnum):
    """Execution result of a single input the engine ran.

    ``new_lines`` on the surrounding ``InputRecord`` is the mechanical
    coverage delta and is independent of this enum: a TARGET_ERROR or
    TIMEOUT input may still carry non-empty ``new_lines`` for the lines
    traced before the failure.
    """

    COVERED_NEW = "covered_new"
    NO_GAIN = "no_gain"
    TARGET_ERROR = "target_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class InputRecord:
    """One input the engine generated, executed, and observed.

    Attributes:
        args: The concrete arguments passed to the target.
        provenance: Where the input came from (seed, solver model,
            plugin event).
        outcome: Whether the input covered new lines, hit duplicates,
            raised, or timed out.
        new_lines: Mechanical coverage delta — lines covered for the
            first time by this input. Populated regardless of outcome.
        error: Exception class plus message when outcome is
            ``TARGET_ERROR`` or ``TIMEOUT``; ``None`` otherwise.
    """

    args: dict[str, Any]
    provenance: Provenance
    outcome: Outcome
    new_lines: frozenset[int]
    error: str | None
