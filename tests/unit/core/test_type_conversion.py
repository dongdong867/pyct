"""Tests for BooleanConverter and NumericConverter."""

from __future__ import annotations


from pyct.core.type_conversion import BooleanConverter, NumericConverter


class TestBooleanConverter:
    """BooleanConverter.normalize_to_bool and to_concolic_bool."""

    def test_normalize_false_int(self):
        assert BooleanConverter.normalize_to_bool(0) is False

    def test_normalize_true_int(self):
        assert BooleanConverter.normalize_to_bool(1) is True

    def test_normalize_bool_true(self):
        assert BooleanConverter.normalize_to_bool(True) is True

    def test_normalize_bool_false(self):
        assert BooleanConverter.normalize_to_bool(False) is False

    def test_normalize_truthy_value(self):
        assert BooleanConverter.normalize_to_bool("nonempty") is True

    def test_normalize_falsy_value(self):
        assert BooleanConverter.normalize_to_bool("") is False

    def test_to_concolic_bool(self, engine):
        from pyct.core.bool import ConcolicBool

        result = BooleanConverter.to_concolic_bool(True, ConcolicBool, engine)
        assert isinstance(result, ConcolicBool)
        assert int.__bool__(result) is True


class TestNumericConverter:
    """NumericConverter.bool_to_int and bool_to_float."""

    def test_bool_to_int_true(self):
        assert NumericConverter.bool_to_int(True) == 1

    def test_bool_to_int_false(self):
        assert NumericConverter.bool_to_int(False) == 0

    def test_bool_to_float_true(self):
        assert NumericConverter.bool_to_float(True) == 1.0

    def test_bool_to_float_false(self):
        assert NumericConverter.bool_to_float(False) == 0.0
