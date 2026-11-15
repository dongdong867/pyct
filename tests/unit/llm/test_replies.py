"""json_items reads the first JSON array in a reply, each item as its own JSON text, and
last_code_block the last fenced code block."""

import pytest

from pyct.llm.replies import json_items, last_code_block


def test_each_item_of_the_array_is_its_own_json_text() -> None:
    assert json_items('[{"x": 1234}, {"x": 7}]') == ('{"x": 1234}', '{"x": 7}')


def test_the_array_may_sit_in_text_or_a_fence() -> None:
    reply = 'Try these [see below]:\n```json\n[{"x": 1}, 2]\n```\nand [{"x": 3}]'

    assert json_items(reply) == ('{"x": 1}', "2")


@pytest.mark.parametrize("reply", ["x should be 1234", "[1, 2", '{"x": 1}', "", "[" * 100_000])
def test_a_reply_with_no_array_python_reads_has_none(reply: str) -> None:
    assert json_items(reply) is None


def test_a_reply_whose_array_holds_a_number_too_long_to_read_has_none() -> None:
    assert json_items('[{"x": ' + "9" * 5000 + "}]") is None


def test_the_last_code_block_is_read_whole_its_language_tag_left_out() -> None:
    reply = "First:\n```\nx = 1\n```\nthen:\n```python\ndef summary(s):\n    return {}\n```\n"

    assert last_code_block(reply) == "def summary(s):\n    return {}\n"


@pytest.mark.parametrize("tag", ["python3", "python ", "c++\t", ""])
def test_a_code_block_s_language_tag_may_hold_digits_signs_and_trailing_spaces(tag: str) -> None:
    assert last_code_block(f"```{tag}\nx = 1\n```") == "x = 1\n"


@pytest.mark.parametrize("reply", ["return {}", "```python def f(): pass```", "", "```\nopen"])
def test_a_reply_with_no_closed_code_block_has_none(reply: str) -> None:
    assert last_code_block(reply) is None
