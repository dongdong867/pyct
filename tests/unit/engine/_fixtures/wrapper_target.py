"""Thin-wrapper target — mirrors the library pattern that exposes the
scope early-exit issue.

``wrapper_target.classify`` has a single-line body that delegates to
``wrapper_helper.classify``. Under classical narrow scope, covering
the one body line triggers ``is_fully_covered`` and terminates the
engine before it explores any of the helper branches. Under a wide
scope that also tracks the helper file, the engine continues to
explore seeds until helper coverage either saturates or the budget
is exhausted.
"""

from __future__ import annotations

from tests.unit.engine._fixtures.wrapper_helper import classify as _classify


def classify(s: str) -> str:
    return _classify(s)
