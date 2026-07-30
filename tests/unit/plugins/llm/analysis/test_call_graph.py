"""Tests for call graph analysis."""

from __future__ import annotations

from pyct.plugins.llm.analysis.call_graph import (
    CallGraphConfig,
    _extract_branch_conditions,
    _extract_call_names,
)


class TestExtractCallNames:
    """_extract_call_names finds function calls in source."""

    def test_simple_calls(self):
        source = "def f():\n    foo()\n    bar(x)"
        names = _extract_call_names(source)
        assert "foo" in names
        assert "bar" in names

    def test_no_calls(self):
        source = "def f():\n    x = 1"
        names = _extract_call_names(source)
        assert names == []


class TestExtractBranchConditions:
    """_extract_branch_conditions finds if/while conditions."""

    def test_if_condition(self):
        source = "def f(x):\n    if x > 10:\n        pass"
        conditions = _extract_branch_conditions(source)
        assert len(conditions) >= 1

    def test_no_branches(self):
        source = "def f():\n    return 1"
        conditions = _extract_branch_conditions(source)
        assert conditions == []


class TestCallGraphConfig:
    """CallGraphConfig frozen dataclass."""

    def test_defaults(self):
        cfg = CallGraphConfig(project_root="/tmp")
        assert cfg.max_depth == 3
