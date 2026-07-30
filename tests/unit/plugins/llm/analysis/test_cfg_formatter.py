"""Tests for CFG formatter."""

from __future__ import annotations

from pyct.plugins.llm.analysis.cfg_extractor import CFGExtractor
from pyct.plugins.llm.analysis.cfg_formatter import format_cfg_for_llm


class TestFormatCFGForLLM:
    """format_cfg_for_llm produces text from CFG."""

    def test_produces_string(self):
        source = "def f(x):\n    if x > 0:\n        return 1\n    return 0"
        extractor = CFGExtractor()
        result = extractor.extract(source)
        text = format_cfg_for_llm(result.nodes, result.edges)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_empty_cfg(self):
        text = format_cfg_for_llm([], [])
        assert isinstance(text, str)
