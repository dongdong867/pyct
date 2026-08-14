"""Tests for LiteralExtractor: extract literals from source code."""

from __future__ import annotations

import ast

from pyct.plugins.llm.analysis.literal_extractor import LiteralExtractor


class TestLiteralExtractor:
    """LiteralExtractor finds string and numeric constants in AST."""

    def test_extract_string_literals(self):
        source = """
def sample(x):
    if x == "magic":
        return "big"
    return "small"
"""
        tree = ast.parse(source)
        extractor = LiteralExtractor()
        extractor.visit(tree)
        assert "magic" in extractor.string_literals

    def test_extract_numeric_literals(self):
        source = """
def sample(x):
    if x > 100:
        return "big"
    return "small"
"""
        tree = ast.parse(source)
        extractor = LiteralExtractor()
        extractor.visit(tree)
        assert 100 in extractor.numeric_literals

    def test_extract_comparisons(self):
        source = """
def sample(x):
    if x > 100:
        return True
"""
        tree = ast.parse(source)
        extractor = LiteralExtractor()
        extractor.visit(tree)
        assert len(extractor.comparisons) >= 1
        assert extractor.comparisons[0]["value"] == 100

    def test_empty_function(self):
        source = """
def sample():
    pass
"""
        tree = ast.parse(source)
        extractor = LiteralExtractor()
        extractor.visit(tree)
        assert len(extractor.string_literals) == 0
        assert len(extractor.numeric_literals) == 0
