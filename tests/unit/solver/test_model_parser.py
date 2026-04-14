"""Tests for ModelParser."""

from __future__ import annotations

import pytest

from pyct.solver.model_parser import ModelParser


class TestParseModel:
    """ModelParser.parse_model extracts variable assignments."""

    def test_int_assignment(self):
        parser = ModelParser()
        model = parser.parse_model(["((x_VAR 42))"], {"x_VAR": "Int"})
        assert model == {"x": 42}

    def test_bool_assignment(self):
        parser = ModelParser()
        model = parser.parse_model(["((flag_VAR true))"], {"flag_VAR": "Bool"})
        assert model == {"flag": True}

    def test_string_assignment(self):
        parser = ModelParser()
        model = parser.parse_model(['((name_VAR "hello"))'], {"name_VAR": "String"})
        assert model == {"name": "hello"}

    def test_real_assignment(self):
        parser = ModelParser()
        model = parser.parse_model(["((val_VAR 3.14))"], {"val_VAR": "Real"})
        assert model["val"] == pytest.approx(3.14)

    def test_negative_int(self):
        parser = ModelParser()
        model = parser.parse_model(["((x_VAR (- 42)))"], {"x_VAR": "Int"})
        assert model == {"x": -42}

    def test_negative_float(self):
        parser = ModelParser()
        model = parser.parse_model(["((x_VAR (- 3.14)))"], {"x_VAR": "Real"})
        assert model["x"] == pytest.approx(-3.14)

    def test_multiple_variables(self):
        parser = ModelParser()
        model = parser.parse_model(
            ["((x_VAR 1))", "((y_VAR 2))"],
            {"x_VAR": "Int", "y_VAR": "Int"},
        )
        assert model == {"x": 1, "y": 2}

    def test_empty_lines_skipped(self):
        parser = ModelParser()
        model = parser.parse_model(
            ["", "((x_VAR 5))", "  "],
            {"x_VAR": "Int"},
        )
        assert model == {"x": 5}

    def test_unknown_variable_skipped(self):
        parser = ModelParser()
        model = parser.parse_model(["((unknown_VAR 99))"], {"x_VAR": "Int"})
        assert model == {}

    def test_string_escapes(self):
        parser = ModelParser()
        model = parser.parse_model(['((s_VAR "line1\\nline2"))'], {"s_VAR": "String"})
        assert model["s"] == "line1\nline2"

    def test_invalid_format_raises(self):
        parser = ModelParser()
        with pytest.raises(ValueError, match="Invalid assignment"):
            parser.parse_model(["bad format"], {"x_VAR": "Int"})

    def test_unsupported_type_raises(self):
        parser = ModelParser()
        with pytest.raises(NotImplementedError, match="Unsupported type"):
            parser.parse_model(["((x_VAR 42))"], {"x_VAR": "CustomType"})


class TestRemoveVarSuffix:
    """_remove_var_suffix strips _VAR from names."""

    def test_removes_suffix(self):
        parser = ModelParser()
        assert parser._remove_var_suffix("x_VAR") == "x"

    def test_no_suffix_unchanged(self):
        parser = ModelParser()
        assert parser._remove_var_suffix("plain") == "plain"
