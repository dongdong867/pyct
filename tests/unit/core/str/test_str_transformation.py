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
