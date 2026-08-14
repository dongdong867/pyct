"""Static call graph analysis via AST.

Walks a target function's AST to discover direct calls to functions
within the project, recursively analyzes them (depth-bounded, cycle-aware),
and produces a structured result for LLM-informed seed generation.
"""

from __future__ import annotations

import ast
import inspect
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from pyct.plugins.llm.analysis.literal_extractor import LiteralExtractor

log = logging.getLogger("pyct.call_graph")


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


@dataclass(frozen=True)
class CallGraphConfig:
    """Configuration for call graph analysis."""

    project_root: str
    max_depth: int = 3


@dataclass(frozen=True)
class AnalyzedFunction:
    """Analysis results for a single function in the call graph."""

    name: str
    qualified_name: str
    file_path: str
    first_line: int
    source: str
    signature: str
    branch_conditions: tuple[str, ...]
    comparisons: tuple[str, ...]
    literals: tuple[str | int | float, ...]
    callees: tuple[str, ...]
    depth: int


@dataclass(frozen=True)
class CallGraphAnalysis:
    """Complete call graph analysis result for a target function."""

    target: AnalyzedFunction
    reachable_functions: dict[str, AnalyzedFunction]
    max_depth_reached: bool
    unresolved_calls: tuple[str, ...]


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def analyze_call_graph(
    func: Callable,
    module: ModuleType,
    config: CallGraphConfig,
) -> CallGraphAnalysis:
    """Analyze the call graph of *func* within the project boundary.

    Returns a ``CallGraphAnalysis`` containing the target function plus
    all reachable callees (up to *config.max_depth* levels deep).
    """
    target = _analyze_single_function(func, module, depth=0)
    visited: set[str] = {target.qualified_name}
    unresolved: list[str] = []
    max_depth_hit = False

    reachable, depth_hit, new_unresolved = _walk_call_graph(
        func,
        module,
        depth=1,
        visited=visited,
        config=config,
    )
    max_depth_hit = max_depth_hit or depth_hit
    unresolved.extend(new_unresolved)

    log.info(
        "[CallGraph] Analyzed %d reachable functions (max_depth_reached=%s)",
        len(reachable),
        max_depth_hit,
    )
    return CallGraphAnalysis(
        target=target,
        reachable_functions=reachable,
        max_depth_reached=max_depth_hit,
        unresolved_calls=tuple(sorted(set(unresolved))),
    )


# ------------------------------------------------------------------
# Recursive traversal
# ------------------------------------------------------------------


def _walk_call_graph(
    func: Callable,
    module: ModuleType,
    depth: int,
    visited: set[str],
    config: CallGraphConfig,
) -> tuple[dict[str, AnalyzedFunction], bool, list[str]]:
    """Recursively walk callees of *func*, returning reachable functions."""
    result: dict[str, AnalyzedFunction] = {}
    unresolved: list[str] = []
    max_depth_hit = False

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return result, max_depth_hit, unresolved

    call_names = _extract_call_names(source)

    for name in call_names:
        callee = _resolve_callee(name, module, config.project_root)
        if callee is None:
            unresolved.append(name)
            continue

        qname = _qualified_name(callee, module)
        if qname in visited:
            continue
        visited.add(qname)

        analyzed = _analyze_single_function(callee, module, depth)
        result[qname] = analyzed

        if depth >= config.max_depth:
            max_depth_hit = True
            continue

        child_result, child_hit, child_unresolved = _walk_call_graph(
            callee,
            module,
            depth + 1,
            visited,
            config,
        )
        result.update(child_result)
        max_depth_hit = max_depth_hit or child_hit
        unresolved.extend(child_unresolved)

    return result, max_depth_hit, unresolved


# ------------------------------------------------------------------
# Single-function analysis
# ------------------------------------------------------------------


def _analyze_single_function(
    func: Callable,
    module: ModuleType,
    depth: int,
) -> AnalyzedFunction:
    """Extract source, branch conditions, literals, and callees for one function."""
    source = _get_source_safe(func)
    sig = _get_signature_safe(func)
    file_path = _get_file_path(func)
    first_line = _get_first_line(func)
    branches = _extract_branch_conditions(source)
    comparisons, literals = _extract_literals(source)
    callees = _extract_call_names(source) if source else []

    return AnalyzedFunction(
        name=func.__name__,
        qualified_name=_qualified_name(func, module),
        file_path=file_path,
        first_line=first_line,
        source=source,
        signature=sig,
        branch_conditions=tuple(branches),
        comparisons=tuple(comparisons),
        literals=tuple(literals),
        callees=tuple(callees),
        depth=depth,
    )


# ------------------------------------------------------------------
# AST extraction helpers
# ------------------------------------------------------------------


def _extract_call_names(source: str) -> list[str]:
    """Extract called function names from source via AST.

    Handles ``ast.Name`` (direct calls like ``foo(x)``) and
    ``ast.Attribute`` where the left-hand side looks like a module
    import (e.g. ``utils.validate(x)``).
    """
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            # Only include module-level attribute calls (e.g. math.sqrt)
            if isinstance(node.func.value, ast.Name):
                names.append(f"{node.func.value.id}.{node.func.attr}")
    return names


def _extract_branch_conditions(source: str) -> list[str]:
    """Extract branch conditions from if/while/assert/raise-if guards."""
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    conditions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While)):
            conditions.append(_safe_unparse(node.test))
        elif isinstance(node, ast.Assert):
            conditions.append(f"assert {_safe_unparse(node.test)}")
    return conditions


def _extract_literals(source: str) -> tuple[list[str], list[str | int | float]]:
    """Extract comparison descriptions and literal boundary values from source.

    Returns (comparisons, literals) where comparisons are human-readable
    strings like ``"Gt: 100"`` and literals are the raw values.
    Filters out docstrings and booleans.
    """
    if not source:
        return [], []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []

    extractor = LiteralExtractor()
    extractor.visit(tree)

    comparisons = [f"{c['op']}: {c['value']!r}" for c in extractor.comparisons]
    raw: set[str | int | float] = set()
    for v in extractor.numeric_literals:
        if not isinstance(v, bool):
            raw.add(v)
    for v in extractor.string_literals:
        if not _looks_like_docstring(v):
            raw.add(v)
    literals: list[str | int | float] = sorted(raw, key=lambda v: str(v))
    return comparisons, literals


def _looks_like_docstring(s: str) -> bool:
    """Heuristic: strings with spaces and ending in '.' are likely docstrings."""
    return len(s) > 30 and " " in s


# ------------------------------------------------------------------
# Resolution helpers
# ------------------------------------------------------------------


def _resolve_callee(
    name: str,
    module: ModuleType,
    project_root: str,
) -> Callable | None:
    """Look up *name* in *module* and return it if within the project.

    Handles both bare names (``"foo"``) and dotted names
    (``"utils.foo"``). Returns ``None`` for stdlib, third-party,
    built-in, or unresolvable names.
    """
    obj = _lookup_in_module(name, module)
    if obj is None or not callable(obj):
        return None
    if not _is_within_project(obj, project_root):
        return None
    return obj


def _lookup_in_module(name: str, module: ModuleType) -> object | None:
    """Resolve a possibly-dotted name against *module*'s namespace."""
    if "." in name:
        parts = name.split(".", 1)
        sub = getattr(module, parts[0], None)
        if sub is None:
            return None
        return getattr(sub, parts[1], None)
    return getattr(module, name, None)


def _is_within_project(func: Callable, project_root: str) -> bool:
    """Return True if *func* is defined within the project root."""
    code = getattr(func, "__code__", None)
    if code is None:
        return False
    file_path = os.path.abspath(code.co_filename)
    root = os.path.abspath(project_root)
    if not file_path.startswith(root):
        return False
    return "site-packages" not in file_path


def _qualified_name(func: Callable, module: ModuleType) -> str:
    """Build a qualified name like ``module.func_name``."""
    mod_name = getattr(module, "__name__", "")
    return f"{mod_name}.{func.__name__}"


# ------------------------------------------------------------------
# Safe accessors
# ------------------------------------------------------------------


def _get_source_safe(func: Callable) -> str:
    try:
        return inspect.getsource(func)
    except (OSError, TypeError):
        return ""


def _get_signature_safe(func: Callable) -> str:
    try:
        return str(inspect.signature(func))
    except (ValueError, TypeError):
        return "()"


def _get_file_path(func: Callable) -> str:
    code = getattr(func, "__code__", None)
    return os.path.abspath(code.co_filename) if code else ""


def _get_first_line(func: Callable) -> int:
    code = getattr(func, "__code__", None)
    return code.co_firstlineno if code else 0


def _safe_unparse(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except (ValueError, TypeError):
        return "..."
