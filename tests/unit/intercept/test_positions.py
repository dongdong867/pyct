"""Where each checked release puts an operand's first instruction, whichever release runs.

The lines-up check holds each rule to the compiler of the release the suite runs on; these
tests take each release's side of a rule that differs between releases on every release.
"""

import ast

import pytest

from pyct.intercept import positions
from pyct.intercept.positions import Parts


def first_line(compare: str) -> int:
    """The line of the first instruction of the compare's left operand."""
    tree = ast.parse(compare, mode="eval")
    left = tree.body.left  # pyrefly: ignore[missing-attribute]
    return Parts(tree).first(left).lineno


@pytest.mark.parametrize(("null_before_callee", "line"), [(True, 1), (False, 2)])
def test_a_plain_call_starts_with_its_null_or_with_its_callee(
    monkeypatch: pytest.MonkeyPatch, null_before_callee: bool, line: int
) -> None:
    # through 3.12 the NULL comes first, at the callee's own position, on the parenthesis's
    # line; from 3.13 it follows the callee, whose object on the next line comes first
    monkeypatch.setattr(positions, "_NULL_BEFORE_CALLEE", null_before_callee)

    assert first_line("(\n x).y(*z) in c") == line
    # a callee on one line is its own first either way
    assert first_line("f(\n x) in c") == 1


@pytest.mark.parametrize(("constant_keys_after_values", "line"), [(True, 2), (False, 1)])
def test_a_dict_of_constant_keys_starts_with_its_first_value_or_its_first_key(
    monkeypatch: pytest.MonkeyPatch, constant_keys_after_values: bool, line: int
) -> None:
    # through 3.13 the constant keys load last, as one tuple; from 3.14 each key comes first
    monkeypatch.setattr(positions, "_CONSTANT_KEYS_AFTER_VALUES", constant_keys_after_values)

    assert first_line("{'a':\n f(), 'b': 2} in c") == line
    # a key that is not a constant comes first either way
    assert first_line("{a:\n f(), 'b': 2} in c") == 1
