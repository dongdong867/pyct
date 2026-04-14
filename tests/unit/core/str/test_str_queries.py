"""Tests for ConcolicStr query methods: find, count, startswith, endswith."""

from __future__ import annotations


from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestFind:
    """str.find — returns index or -1."""

    def test_find_existing(self, engine):
        cs = ConcolicStr("hello world", "x", engine)
        result = cs.find("world")
        assert unwrap_concolic(result) == 6

    def test_find_missing(self, engine):
        cs = ConcolicStr("hello world", "x", engine)
        result = cs.find("xyz")
        assert unwrap_concolic(result) == -1


class TestCount:
    """str.count — non-overlapping occurrences."""

    def test_count_multiple(self, engine):
        cs = ConcolicStr("abcabc", "x", engine)
        result = cs.count("abc")
        assert unwrap_concolic(result) == 2

    def test_count_zero(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.count("xyz")
        assert unwrap_concolic(result) == 0


class TestStartsWith:
    """str.startswith — prefix check."""

    def test_startswith_true(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.startswith("hel")
        assert unwrap_concolic(result) is True

    def test_startswith_false(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.startswith("xyz")
        assert unwrap_concolic(result) is False


class TestEndsWith:
    """str.endswith — suffix check."""

    def test_endswith_true(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.endswith("llo")
        assert unwrap_concolic(result) is True

    def test_endswith_false(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.endswith("xyz")
        assert unwrap_concolic(result) is False
