"""Unit tests for pyct.plugins.llm.parser — response text -> input dicts.

Parses LLM responses in three common shapes:
- Markdown code fence: ```python [{"x": 1}] ```
- Markdown code fence plain: ``` [{"x": 1}] ```
- Raw literal without fencing

Falls back to a restricted ``eval`` for LLM-generated expressions like
``"a" * 5`` that ``ast.literal_eval`` rejects but which represent the
intended test input.

``parse_input_list`` returns a ``(list[dict], int)`` tuple so callers
(the LLM plugin, in particular) can accumulate a parse-failed count
into the engine's ``gen_parse_failed`` counter. Failure rules:

- ``None`` content → no candidates, 0 fails.
- Whole response can't be eval'd into a list → 1 fail (the entire
  response counts as one failed candidate).
- List parsed but some entries are non-dict / empty after sanitize →
  fails = (parsed list len) − (returned list len).
"""

from __future__ import annotations


class TestExtractInputList:
    def test_parse_code_fence_python(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = 'Here are the inputs:\n```python\n[{"x": 1}, {"x": 2}]\n```\n'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 1}, {"x": 2}]
        assert fails == 0

    def test_parse_code_fence_plain(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '```\n[{"x": 5}]\n```'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 5}]
        assert fails == 0

    def test_parse_raw_literal(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": 7}]'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 7}]
        assert fails == 0

    def test_parse_single_dict_returns_empty_list_with_one_fail(self):
        """A bare dict is not a list — whole response counts as one failed candidate."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '{"x": 1}'
        inputs, fails = parse_input_list(content)
        assert inputs == []
        assert fails == 1

    def test_parse_garbage_returns_empty_with_one_fail(self):
        from pyct.plugins.llm.parser import parse_input_list

        inputs, fails = parse_input_list("this is not python")
        assert inputs == []
        assert fails == 1

    def test_parse_none_returns_empty_with_zero_fails(self):
        """None content — no parse attempt, no failed candidate."""
        from pyct.plugins.llm.parser import parse_input_list

        inputs, fails = parse_input_list(None)
        assert inputs == []
        assert fails == 0

    def test_parse_multiplication_expression_via_fallback(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": "a" * 5}]'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": "aaaaa"}]
        assert fails == 0


class TestPartialFailCount:
    """Mixed-validity lists count drops as fails."""

    def test_non_dict_entries_count_as_fails(self):
        """[{"x": 1}, "garbage", 3] — two entries get dropped → 2 fails."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": 1}, "garbage", 3]'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 1}]
        assert fails == 2

    def test_empty_dict_after_sanitize_counts_as_fail(self):
        """{} sanitizes to None → drop → 1 fail."""
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": 1}, {}]'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 1}]
        assert fails == 1

    def test_all_valid_list_has_zero_fails(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"x": 1}, {"y": 2}, {"z": 3}]'
        inputs, fails = parse_input_list(content)
        assert inputs == [{"x": 1}, {"y": 2}, {"z": 3}]
        assert fails == 0

    def test_empty_list_has_zero_fails(self):
        """Empty list is a successful parse with no candidates."""
        from pyct.plugins.llm.parser import parse_input_list

        inputs, fails = parse_input_list("[]")
        assert inputs == []
        assert fails == 0


class TestSanitizerStripsNonPickleableValues:
    def test_top_level_lambda_stripped(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"callback": lambda: None}]'
        inputs, _ = parse_input_list(content)
        assert inputs == [{"callback": None}]

    def test_nested_lambda_in_dict_stripped(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"curve": {"_domain": {"convert": lambda: None}}, "x": 1}]'
        inputs, _ = parse_input_list(content)
        assert inputs == [{"curve": {"_domain": {"convert": None}}, "x": 1}]

    def test_nested_lambda_in_list_stripped(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = '[{"handlers": [lambda: 1, lambda: 2]}]'
        inputs, _ = parse_input_list(content)
        assert inputs == [{"handlers": [None, None]}]

    def test_sanitized_output_is_pickle_safe(self):
        """The strongest invariant: whatever comes out must pickle cleanly
        so it can cross the isolated_runner subprocess boundary."""
        import pickle

        from pyct.plugins.llm.parser import parse_input_list

        content = (
            '[{"curve": {"_domain": {"convert": lambda: None}, '
            '"validators": [lambda: True]}, "x": 1, "y": 2}]'
        )
        inputs, _ = parse_input_list(content)
        pickle.dumps(inputs)  # must not raise

    def test_scalars_and_structures_preserved(self):
        from pyct.plugins.llm.parser import parse_input_list

        content = (
            '[{"s": "hello", "i": 42, "f": 3.14, "b": True, "n": None, '
            '"lst": [1, 2, 3], "nested": {"k": "v"}}]'
        )
        inputs, _ = parse_input_list(content)
        assert inputs == [
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
    """``parse_single_input`` keeps its dict|None shape (no fail count)."""

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
