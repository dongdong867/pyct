"""Literal Extractor for Source-Code-Guided Fuzzing.

This module extracts literals (strings, numbers) from the source code of target
functions to guide fuzzing when PyCT cannot generate symbolic constraints.

This is critical for handling cases like:
  if items[0] == "special":  # Need to fuzz with "special"
  if "target" in items:       # Need to fuzz with "target"
  if x > 100:                 # Need to fuzz with values around 100
"""

from __future__ import annotations

import ast
import inspect
import logging
from typing import Any, Dict, List, Set

log = logging.getLogger("pyct.literal_extractor")


class LiteralExtractor(ast.NodeVisitor):
    """Extract literals from Python source code."""

    def __init__(self):
        self.string_literals: Set[str] = set()
        self.numeric_literals: Set[int | float] = set()
        self.comparisons: List[Dict[str, Any]] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        """Extract comparison operations and their literals."""
        # Extract the comparison details
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(comparator, ast.Constant):
                value = comparator.value
                op_name = op.__class__.__name__

                # Store comparison info
                self.comparisons.append(
                    {"op": op_name, "value": value, "type": type(value).__name__}
                )

                # Also store the literal
                if isinstance(value, str):
                    self.string_literals.add(value)
                elif isinstance(value, (int, float)):
                    self.numeric_literals.add(value)

            # Handle "x in container" - the literal is the left side of 'In' operator
            if isinstance(op, ast.In) and isinstance(node.left, ast.Constant):
                value = node.left.value
                self.comparisons.append(
                    {"op": "In", "value": value, "type": type(value).__name__}
                )
                if isinstance(value, str):
                    self.string_literals.add(value)
                elif isinstance(value, (int, float)):
                    self.numeric_literals.add(value)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Extract all constant literals."""
        value = node.value
        if isinstance(value, str) and value:  # Non-empty strings
            # Filter out multi-line strings (docstrings, etc.)
            if "\n" not in value:
                self.string_literals.add(value)
        elif isinstance(value, (int, float)):
            self.numeric_literals.add(value)
        self.generic_visit(node)


def extract_literals_from_function(func: Any) -> Dict[str, Any]:
    """Extract string and numeric literals from a function's source code."""
    try:
        source = inspect.getsource(func)
        tree = ast.parse(source)
        extractor = LiteralExtractor()
        extractor.visit(tree)
        result = _build_literal_result(extractor)
        log.info(
            "Extracted %d comparison string literals, %d total string literals from %s",
            len(result["comparison_strings"]),
            len(result["strings"]),
            func.__name__,
        )
        log.debug("Comparison strings: %s", result["comparison_strings"])
        log.debug("All strings: %s", result["strings"])
        return result
    except Exception as e:
        log.debug("Failed to extract literals from %s: %s", func, e)
        return _empty_literal_result()


def _build_literal_result(extractor: LiteralExtractor) -> Dict[str, Any]:
    comparison_strings = [
        c["value"] for c in extractor.comparisons if isinstance(c["value"], str)
    ]
    comparison_numbers = [
        c["value"]
        for c in extractor.comparisons
        if isinstance(c["value"], (int, float))
    ]
    other_strings = sorted(
        s for s in extractor.string_literals if s not in comparison_strings
    )
    other_numbers = sorted(
        n for n in extractor.numeric_literals if n not in comparison_numbers
    )
    return {
        "strings": sorted(comparison_strings) + other_strings,
        "numbers": sorted(comparison_numbers) + other_numbers,
        "comparisons": extractor.comparisons,
        "comparison_strings": sorted(comparison_strings),
        "comparison_numbers": sorted(comparison_numbers),
    }


def _empty_literal_result() -> Dict[str, Any]:
    return {
        "strings": [],
        "numbers": [],
        "comparisons": [],
        "comparison_strings": [],
        "comparison_numbers": [],
    }


def extract_literals_from_module_function(
    module_path: str, func_name: str
) -> Dict[str, Any]:
    """
    Extract literals from a function specified by module path and name.

    Args:
        module_path: Module path (e.g., 'examples.dft.integration_test')
        func_name: Function name

    Returns:
        Dictionary with extracted literals
    """
    try:
        import importlib

        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        return extract_literals_from_function(func)
    except Exception as e:
        log.error(
            "Failed to extract literals from %s::%s: %s", module_path, func_name, e
        )
        return _empty_literal_result()
