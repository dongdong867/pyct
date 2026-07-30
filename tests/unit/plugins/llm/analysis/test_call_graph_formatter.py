"""Tests for call graph formatter."""

from __future__ import annotations

from unittest.mock import MagicMock

from pyct.plugins.llm.analysis.call_graph_formatter import format_call_graph_for_llm


class TestFormatCallGraphForLLM:
    """format_call_graph_for_llm produces text from analysis."""

    def test_produces_string(self):
        analysis = MagicMock()
        analysis.target = MagicMock()
        analysis.target.name = "func"
        analysis.target.source = "def func(): pass"
        analysis.target.branch_conditions = []
        analysis.target.comparisons = []
        analysis.target.literals = ([], [])
        analysis.reachable_functions = {}
        analysis.unresolved_calls = []

        text = format_call_graph_for_llm(analysis)
        assert isinstance(text, str)
