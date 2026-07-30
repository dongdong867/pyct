"""Tests for CFG extraction."""

from __future__ import annotations

from pyct.plugins.llm.analysis.cfg_extractor import CFGExtractor, CFGNode


class TestCFGExtractor:
    """CFGExtractor builds control flow graphs from source."""

    def test_simple_function(self):
        source = "def f(x):\n    if x > 0:\n        return 1\n    return 0"
        extractor = CFGExtractor()
        result = extractor.extract(source)
        assert len(result.nodes) >= 1
        assert result.entry_node is not None

    def test_empty_function(self):
        source = "def f():\n    pass"
        extractor = CFGExtractor()
        result = extractor.extract(source)
        assert len(result.nodes) >= 1


class TestCFGNode:
    """CFGNode frozen dataclass."""

    def test_construction(self):
        node = CFGNode(
            id=1,
            line_number=10,
            node_type="if",
            code_snippet="if x > 0:",
            condition="x > 0",
        )
        assert node.id == 1
        assert node.condition == "x > 0"
