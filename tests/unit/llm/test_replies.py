"""json_items reads the first JSON array in a reply, each item as its own JSON text."""

import pytest

from pyct.llm.replies import json_items


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
