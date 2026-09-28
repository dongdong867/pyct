"""Acceptance tests for the refuse-an-attribute-a-plain-number-refuses bug.

A tracked int, bool or float refuses a set or a delete of an attribute as a plain one does, with
plain Python's error in the running release's words, and keeps its own fields where pyct wrote
them. Each test runs pyct through the command line, in its default own-process mode, and reads
plain Python's answer from the same fixture called on a plain value in this test run.
"""

import pytest

from targets.types import attributes
from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_ints import forks_of
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    covers_plainly,
    line_of,
    python_raise,
    raised,
)

TARGET = "targets.types.attributes"
FILE = REPO_ROOT / "targets" / "types" / "attributes.py"
# each seed, and the plain value of its own type that plain Python is asked about
SEEDS = [('{"x": 3}', 3), ('{"x": true}', True), ('{"x": 2.5}', 2.5)]
SEED_IDS = ["int", "bool", "float"]


# refuse-an-attribute-a-plain-number-refuses-refuses-a-new-attribute
@pytest.mark.parametrize("function", ["set_new", "set_by_name"])
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_refuses_a_new_attribute(function: str, seed: str, plain: object) -> None:
    assert getattr(attributes, function)(plain) == "refused"
    line = covers_plainly(f"{TARGET}::{function}", seed, FILE, "refused")
    assert line_of(FILE, 'return "set"', function) not in covered_in(line, str(FILE))


# refuse-an-attribute-a-plain-number-refuses-says-what-python-says
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_says_what_python_says(seed: str, plain: object) -> None:
    result = run_pyct(f"{TARGET}::only_set", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: attributes.only_set(plain))
    assert isinstance(error, AttributeError)
    raised(first_line(result.stdout), error)


# refuse-an-attribute-a-plain-number-refuses-refuses-a-delete
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_refuses_a_delete(seed: str, plain: object) -> None:
    result = run_pyct(f"{TARGET}::set_then_delete", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: attributes.set_then_delete(plain))
    assert isinstance(error, AttributeError)
    raised(first_line(result.stdout), error)


# refuse-an-attribute-a-plain-number-refuses-refuses-a-compare-result
def test_refuses_a_compare_result() -> None:
    assert attributes.set_on_a_compare(3) == "refused"
    line = covers_plainly(f"{TARGET}::set_on_a_compare", '{"x": 3}', FILE, "refused")
    assert line_of(FILE, 'return "set"', "set_on_a_compare") not in covered_in(line, str(FILE))


# refuse-an-attribute-a-plain-number-refuses-refuses-a-name-pyct-keeps
@pytest.mark.parametrize("seed", ['{"x": 3}', '{"x": 2.5}'], ids=["int", "float"])
def test_refuses_a_name_pyct_keeps(seed: str) -> None:
    result = run_pyct(f"{TARGET}::set_pyct_s_names", seed)

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(line)] == [
        ([">", "x", 10], False)
    ]
    big = line_of(FILE, 'return "big"', "set_pyct_s_names")
    assert any(big in covered_in(solved, str(FILE)) for solved in input_lines(result.stdout)[1:])
