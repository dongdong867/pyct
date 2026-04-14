"""Tests for ConcolicStr manipulation: replace, split, strip, splitlines."""

from __future__ import annotations

from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestReplace:
    """str.replace — substring replacement."""

    def test_replace_all(self, engine):
        cs = ConcolicStr("aabbcc", "x", engine)
        result = cs.replace("bb", "XX")
        assert unwrap_concolic(result) == "aaXXcc"

    def test_replace_with_count(self, engine):
        cs = ConcolicStr("ababab", "x", engine)
        result = cs.replace("ab", "X", 2)
        assert unwrap_concolic(result) == "XXab"


class TestSplit:
    """str.split — split by delimiter."""

    def test_split_by_delimiter(self, engine):
        cs = ConcolicStr("a,b,c", "x", engine)
        parts = cs.split(",")
        assert len(parts) == 3
        assert unwrap_concolic(parts[0]) == "a"
        assert unwrap_concolic(parts[1]) == "b"
        assert unwrap_concolic(parts[2]) == "c"


class TestStrip:
    """str.strip — leading/trailing whitespace removal."""

    def test_strip_whitespace(self, engine):
        cs = ConcolicStr("  hello  ", "x", engine)
        result = cs.strip()
        assert unwrap_concolic(result) == "hello"


class TestSplitlines:
    """str.splitlines — split by line boundaries."""

    def test_splitlines(self, engine):
        cs = ConcolicStr("a\nb\nc", "x", engine)
        parts = cs.splitlines()
        concrete_parts = [unwrap_concolic(p) for p in parts]
        assert concrete_parts == ["a", "b", "c"]


class TestStrManipulationErrorCases:
    """Error paths: empty separator, negative replace count, empty strip."""

    def test_split_with_empty_separator_raises(self, engine):
        import pytest

        cs = ConcolicStr("abc", "x", engine)
        with pytest.raises(ValueError, match="empty separator"):
            cs.split("")

    def test_replace_empty_old_inserts_between_every_character(self, engine):
        # "abc".replace("", "X") == "XaXbXcX" — Python str semantics
        cs = ConcolicStr("abc", "x", engine)
        result = cs.replace("", "X")
        assert unwrap_concolic(result) == "XaXbXcX"

    def test_replace_negative_count_replaces_all(self, engine):
        # Negative count in Python str.replace means "replace all"
        cs = ConcolicStr("ababab", "x", engine)
        result = cs.replace("ab", "X", -1)
        assert unwrap_concolic(result) == "XXX"

    def test_strip_on_empty_string_returns_empty(self, engine):
        cs = ConcolicStr("", "x", engine)
        result = cs.strip()
        assert unwrap_concolic(result) == ""
