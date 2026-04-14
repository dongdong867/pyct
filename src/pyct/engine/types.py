"""Type aliases for engine data structures."""

from __future__ import annotations

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
