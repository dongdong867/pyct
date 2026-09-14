"""The harness demands the summary line, so every line-counting test checks it too."""

import pytest

from tests.acceptance.harness import input_lines


def test_input_lines_demands_the_summary() -> None:
    # a run that lost its summary would otherwise read as one plain input line
    with pytest.raises(AssertionError):
        input_lines('{"args": {"x": 3}}\n')
