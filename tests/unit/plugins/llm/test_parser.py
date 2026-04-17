"""Unit tests for pyct.plugins.llm.parser — response text -> input dicts.

Parses LLM responses in three common shapes:
- Markdown code fence: ```python [{"x": 1}] ```
- Markdown code fence plain: ``` [{"x": 1}] ```
- Raw literal without fencing

Falls back to a restricted ``eval`` for LLM-generated expressions like
``"a" * 5`` that ``ast.literal_eval`` rejects but which represent the
intended test input.
"""

from __future__ import annotations


class TestExtractInputList:
    def test_parse_code_fence_python(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = 'Here are the inputs:\n```python\n[{"x": 1}, {"x": 2}]\n```\n'
        assert parse_input_list(content) == [{"x": 1}, {"x": 2}]

    def test_parse_code_fence_plain(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '```\n[{"x": 5}]\n```'
        assert parse_input_list(content) == [{"x": 5}]

    def test_parse_raw_literal(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": 7}]'
        assert parse_input_list(content) == [{"x": 7}]

    def test_parse_single_dict_returns_empty_list(self):
        """A bare dict is not a list; callers expecting list semantics
        must handle that (the seed handler returns [] in this case)."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '{"x": 1}'
        assert parse_input_list(content) == []

    def test_parse_garbage_returns_empty(self):
        from pyct.plugins.llm.parser import parse_input_list

        assert parse_input_list("this is not python") == []

    def test_parse_none_returns_empty(self):
        from pyct.plugins.llm.parser import parse_input_list

        assert parse_input_list(None) == []

    def test_parse_multiplication_expression_via_fallback(self):
        """LLMs sometimes emit ``[{"x": "a" * 5}]`` despite instructions.
        ast.literal_eval rejects the multiplication; the restricted eval
        fallback accepts it."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": "a" * 5}]'
        assert parse_input_list(content) == [{"x": "aaaaa"}]


class TestSanitizerStripsNonPickleableValues:
    """LLM-eval fallback can produce lambdas, functions, and other non-picklable
    objects. Seed dicts cross a multiprocessing.spawn boundary in isolated mode,
    so every nested value must be pickle-safe. The sanitizer replaces unsafe
    values with None and recurses into nested dicts/lists.
    """

    def test_top_level_lambda_stripped(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"callback": lambda: None}]'
        assert parse_input_list(content) == [{"callback": None}]

    def test_nested_lambda_in_dict_stripped(self):
        """Reproduces the sympy EllipticCurvePoint pickle failure: LLM
        returns a seed whose ``curve`` value is a dict containing lambdas."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"curve": {"_domain": {"convert": lambda: None}}, "x": 1}]'
        result = parse_input_list(content)
        assert result == [{"curve": {"_domain": {"convert": None}}, "x": 1}]

    def test_nested_lambda_in_list_stripped(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"handlers": [lambda: 1, lambda: 2]}]'
        result = parse_input_list(content)
        assert result == [{"handlers": [None, None]}]

    def test_sanitized_output_is_pickle_safe(self):
        """The strongest invariant: whatever comes out must pickle cleanly
        so it can cross the isolated_runner subprocess boundary."""
        import pickle

        from pyct.plugins.llm.parser import parse_input_list

        content = (
            '[{"curve": {"_domain": {"convert": lambda: None}, '
            '"validators": [lambda: True]}, "x": 1, "y": 2}]'
        )
        result = parse_input_list(content)
        pickle.dumps(result)  # must not raise

    def test_scalars_and_structures_preserved(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = (
            '[{"s": "hello", "i": 42, "f": 3.14, "b": True, "n": None, '
            '"lst": [1, 2, 3], "nested": {"k": "v"}}]'
        )
        assert parse_input_list(content) == [
            {
                "s": "hello",
                "i": 42,
                "f": 3.14,
                "b": True,
                "n": None,
                "lst": [1, 2, 3],
                "nested": {"k": "v"},
            }
        ]


class TestExtractSingleInput:
    def test_parse_single_dict(self):
        from pyct.plugins.llm.parser import parse_single_input

        content = '{"x": 42}'
        assert parse_single_input(content) == {"x": 42}

    def test_parse_list_returns_first_dict(self):
        from pyct.plugins.llm.parser import parse_single_input

        content = '[{"x": 1}, {"x": 2}]'
        assert parse_single_input(content) == {"x": 1}

    def test_parse_empty_list_returns_none(self):
        from pyct.plugins.llm.parser import parse_single_input

        content = "[]"
        assert parse_single_input(content) is None

    def test_parse_garbage_returns_none(self):
        from pyct.plugins.llm.parser import parse_single_input

        assert parse_single_input("garbage") is None

    def test_parse_none_returns_none(self):
        from pyct.plugins.llm.parser import parse_single_input

        assert parse_single_input(None) is None
