"""Tests for ConcolicStr character classification: isdigit, isalpha, etc."""

from __future__ import annotations

from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestIsDigit:
    """str.isdigit — all-digits check."""

    def test_isdigit_true(self, engine):
        cs = ConcolicStr("123", "x", engine)
        result = cs.isdigit()
        assert unwrap_concolic(result) is True

    def test_isdigit_false(self, engine):
        cs = ConcolicStr("12a", "x", engine)
        result = cs.isdigit()
        assert unwrap_concolic(result) is False


class TestIsAlpha:
    """str.isalpha — all-alphabetic check."""

    def test_isalpha_true(self, engine):
        cs = ConcolicStr("abc", "x", engine)
        result = cs.isalpha()
        assert unwrap_concolic(result) is True

    def test_isalpha_false(self, engine):
        cs = ConcolicStr("ab1", "x", engine)
        result = cs.isalpha()
        assert unwrap_concolic(result) is False


class TestIsAlnum:
    """str.isalnum — alphanumeric check."""

    def test_isalnum_true(self, engine):
        cs = ConcolicStr("abc123", "x", engine)
        result = cs.isalnum()
        assert unwrap_concolic(result) is True

    def test_isalnum_false(self, engine):
        cs = ConcolicStr("abc!", "x", engine)
        result = cs.isalnum()
        assert unwrap_concolic(result) is False


class TestIsLower:
    """str.islower — lowercase check."""

    def test_islower_true(self, engine):
        cs = ConcolicStr("abc", "x", engine)
        result = cs.islower()
        assert unwrap_concolic(result) is True

    def test_islower_false(self, engine):
        cs = ConcolicStr("Abc", "x", engine)
        result = cs.islower()
        assert unwrap_concolic(result) is False


class TestIsUpper:
    """str.isupper — uppercase check."""

    def test_isupper_true(self, engine):
        cs = ConcolicStr("ABC", "x", engine)
        result = cs.isupper()
        assert unwrap_concolic(result) is True

    def test_isupper_false(self, engine):
        cs = ConcolicStr("Abc", "x", engine)
        result = cs.isupper()
        assert unwrap_concolic(result) is False


class TestCharacterChecksOnEmptyString:
    """Python str semantics: all char-check methods return False on ''."""

    def test_isdigit_empty_is_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert unwrap_concolic(cs.isdigit()) is False

    def test_isalpha_empty_is_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert unwrap_concolic(cs.isalpha()) is False

    def test_isalnum_empty_is_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert unwrap_concolic(cs.isalnum()) is False

    def test_islower_empty_is_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert unwrap_concolic(cs.islower()) is False

    def test_isupper_empty_is_false(self, engine):
        cs = ConcolicStr("", "x", engine)
        assert unwrap_concolic(cs.isupper()) is False
