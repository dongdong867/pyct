"""Tests for ConcolicStr binary operations: concatenation, repetition, slicing, len, contains."""

from __future__ import annotations


from pyct.core.int import ConcolicInt
from pyct.core.str.str import ConcolicStr
from pyct.utils.concolic_converter import unwrap_concolic


class TestConcatenation:
    """String concatenation via __add__."""

    def test_add_two_concolic_str(self, engine):
        a = ConcolicStr("hello", "a", engine)
        b = ConcolicStr(" world", "b", engine)
        result = a + b
        assert unwrap_concolic(result) == "hello world"

    def test_add_concolic_and_primitive(self, engine):
        a = ConcolicStr("hello", "a", engine)
        result = a + " world"
        assert unwrap_concolic(result) == "hello world"


class TestRepetition:
    """String repetition via __mul__."""

    def test_mul_by_int(self, engine):
        cs = ConcolicStr("ab", "x", engine)
        result = cs * 3
        assert unwrap_concolic(result) == "ababab"

    def test_rmul(self, engine):
        cs = ConcolicStr("ab", "x", engine)
        result = 2 * cs
        assert unwrap_concolic(result) == "abab"


class TestSlicing:
    """__getitem__ for indexing and slicing."""

    def test_index_single_char(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs[0]
        assert unwrap_concolic(result) == "h"

    def test_slice(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs[1:4]
        assert unwrap_concolic(result) == "ell"


class TestLen:
    """__len__ returns ConcolicInt."""

    def test_len_returns_concolic_int(self, engine):
        cs = ConcolicStr("hello", "x", engine)
        result = cs.__len__()
        assert isinstance(result, ConcolicInt)
        assert unwrap_concolic(result) == 5

    def test_len_symbolic_expr(self, engine):
        cs = ConcolicStr("abc", "x", engine)
        result = cs.__len__()
        assert result.expr == ["str.len", cs]


class TestContains:
    """__contains__ returns ConcolicBool."""

    def test_contains_found(self, engine):
        cs = ConcolicStr("hello world", "x", engine)
        result = cs.__contains__("world")
        assert unwrap_concolic(result) is True

    def test_contains_not_found(self, engine):
        cs = ConcolicStr("hello world", "x", engine)
        result = cs.__contains__("xyz")
        assert unwrap_concolic(result) is False
