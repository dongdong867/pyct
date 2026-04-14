"""Tests for ConcolicStr transformations: lower, upper, join."""

from __future__ import annotations

from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestLower:
    """str.lower — case conversion."""

    def test_lower(self, engine):
        cs = ConcolicStr("HELLO", "x", engine)
        result = cs.lower()
        assert unwrap_concolic(result) == "hello"


class TestUpper:
    """str.upper — case conversion."""

    def test_upper(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.upper()
        assert unwrap_concolic(result) == "HELLO"


class TestJoin:
    """str.join — join iterable."""

    def test_join_iterable(self, engine):
        cs = ConcolicStr(",", "x", engine)
        result = cs.join(["a", "b", "c"])
        assert unwrap_concolic(result) == "a,b,c"


class TestTransformationEdge:
    """Edge and degenerate inputs for transformations."""

    def test_lower_on_empty_string(self, engine):
        cs = ConcolicStr("", "x", engine)
        result = cs.lower()
        assert unwrap_concolic(result) == ""

    def test_upper_on_already_upper_is_idempotent(self, engine):
        cs = ConcolicStr("HELLO", "x", engine)
        result = cs.upper()
        assert unwrap_concolic(result) == "HELLO"

    def test_join_empty_iterable_returns_empty_string(self, engine):
        cs = ConcolicStr(",", "x", engine)
        result = cs.join([])
        assert unwrap_concolic(result) == ""

    def test_join_single_element_ignores_separator(self, engine):
        cs = ConcolicStr(",", "x", engine)
        result = cs.join(["only"])
        assert unwrap_concolic(result) == "only"
