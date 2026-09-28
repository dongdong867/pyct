"""Acceptance tests for the name-int-in-a-tracked-int-s-type-error bug.

A message Python writes with a value's type names a tracked value's base type, as it names a
plain value's: `int`, `bool`, `float`, `str`, `list`, `dict`, `range` and the dict views. Each
test runs pyct through the command line, and reads plain Python's messages from the same fixture
called on plain values in this test run, since Python's words differ between releases.
"""

import pytest

from targets.types import messages
from tests.acceptance.harness import REPO_ROOT, first_line, run_pyct
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    line_of,
    python_raise,
    raised,
)

TARGET = "targets.types.messages"
FILE = REPO_ROOT / "targets" / "types" / "messages.py"
# each number seed, and the plain value of its own type that plain Python is asked about
NUMBERS = [('{"x": 3}', 3), ('{"x": true}', True), ('{"x": 2.5}', 2.5)]
NUMBER_IDS = ["int", "bool", "float"]
OTHERS = [('{"x": "ab"}', "ab"), ('{"x": [1]}', [1]), ('{"x": {"k": 1}}', {"k": 1})]
OTHER_IDS = ["str", "list", "dict"]


def covers_same(function: str, seed: str, *argv: str) -> dict[str, object]:
    """Run the target, and check the seed's line covers `return "same"` and not
    `return "differs"`, with no failure. The line comes back for more checks."""
    result = run_pyct(f"{TARGET}::{function}", seed, *argv)

    assert result.returncode == 0, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    covered = covered_in(line, str(FILE))
    assert line_of(FILE, 'return "same"', function) in covered, line
    assert line_of(FILE, 'return "differs"', function) not in covered, line
    return line


# name-int-in-a-tracked-int-s-type-error-takes-the-path-python-takes
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_takes_the_path_python_takes(where: tuple[str, ...]) -> None:
    assert messages.shift_check(3) == "same"
    line = covers_same("shift_check", '{"x": 3}', *where)
    assert line["downgrades"] == []


# name-int-in-a-tracked-int-s-type-error-names-the-type-in-each-form
@pytest.mark.parametrize(("seed", "plain"), NUMBERS, ids=NUMBER_IDS)
def test_names_the_type_in_each_form(seed: str, plain: object) -> None:
    assert messages.each_form(plain) == "same"
    covers_same("each_form", seed)


# name-int-in-a-tracked-int-s-type-error-names-bool-for-a-compare-result
def test_names_bool_for_a_compare_result() -> None:
    assert messages.compare_result(3) == "same"
    covers_same("compare_result", '{"x": 3}')


# name-int-in-a-tracked-int-s-type-error-reports-python-s-words
@pytest.mark.parametrize(("seed", "plain"), NUMBERS, ids=NUMBER_IDS)
def test_reports_python_s_words(seed: str, plain: object) -> None:
    result = run_pyct(f"{TARGET}::shift", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: messages.shift(plain))
    assert isinstance(error, TypeError)
    raised(first_line(result.stdout), error)
    assert f"ended target raised: TypeError: {error}" in result.stderr.splitlines()


# name-int-in-a-tracked-int-s-type-error-names-each-other-class
@pytest.mark.parametrize(("seed", "plain"), OTHERS, ids=OTHER_IDS)
def test_names_each_other_class(seed: str, plain: object) -> None:
    assert messages.each_other_form(plain) == "same"
    covers_same("each_other_form", seed)


# name-int-in-a-tracked-int-s-type-error-names-a-dict-s-views
def test_names_a_dict_s_views() -> None:
    assert messages.each_view({"k": 1}) == "same"
    covers_same("each_view", '{"d": {"k": 1}}')


# name-int-in-a-tracked-int-s-type-error-names-a-range
def test_names_a_range() -> None:
    assert messages.ranged(2) == "same"
    covers_same("ranged", '{"n": 2}')
