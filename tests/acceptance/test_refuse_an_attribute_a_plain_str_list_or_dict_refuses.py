"""Acceptance tests for the refuse-an-attribute-a-plain-str-list-or-dict-refuses bug.

A tracked str, list, dict or range, and a tracked dict's views, refuse a set or a delete of an
attribute as the plain value does, with plain Python's error in the running release's words, and
keep their own fields where pyct wrote them. Each test runs pyct through the command line, in its
default own-process mode, and reads plain Python's answer from the same fixture called on a plain
value in this test run.
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
SEEDS = [('{"x": "ab"}', "ab"), ('{"x": [1]}', [1]), ('{"x": {"k": 1}}', {"k": 1})]
SEED_IDS = ["str", "list", "dict"]
# a str of one character is built as one too, and refuses as a longer one does
ONE_CHARACTER = ('{"x": "a"}', "a")


def _forks(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each fork's expression and the side the input took."""
    return [(fork["expression"], fork["taken"]) for fork in forks_of(line)]


def _solved_covers(stdout: str, function: str, returned: str) -> bool:
    """Whether an input the solver found covers the line that returns ``returned``."""
    wanted = line_of(FILE, f'return "{returned}"', function)
    return any(wanted in covered_in(line, str(FILE)) for line in input_lines(stdout)[1:])


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-a-new-attribute
@pytest.mark.parametrize("function", ["set_new", "set_by_name"])
@pytest.mark.parametrize(
    ("seed", "plain"), [*SEEDS, ONE_CHARACTER], ids=[*SEED_IDS, "one-character"]
)
def test_refuses_a_new_attribute(function: str, seed: str, plain: object) -> None:
    assert getattr(attributes, function)(plain) == "refused"
    line = covers_plainly(f"{TARGET}::{function}", seed, FILE, "refused")
    assert line_of(FILE, 'return "set"', function) not in covered_in(line, str(FILE))


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-says-what-python-says
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_says_what_python_says(seed: str, plain: object) -> None:
    result = run_pyct(f"{TARGET}::only_set", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: attributes.only_set(plain))
    assert isinstance(error, AttributeError)
    raised(first_line(result.stdout), error)


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-a-delete
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_refuses_a_delete(seed: str, plain: object) -> None:
    result = run_pyct(f"{TARGET}::set_then_delete", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: attributes.set_then_delete(plain))
    assert isinstance(error, AttributeError)
    raised(first_line(result.stdout), error)


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-on-a-computed-value
def test_refuses_on_a_computed_value() -> None:
    seed = '{"s": "ab", "xs": [1]}'
    assert attributes.set_on_computed("ab", [1]) == "small"
    set_on = run_pyct(f"{TARGET}::set_on_computed", seed)
    untouched = run_pyct(f"{TARGET}::computed_untouched", seed)

    assert set_on.returncode == 0, set_on.stderr
    line = first_line(set_on.stdout)
    assert line["failure"] is None, line
    covered = covered_in(line, str(FILE))
    assert line_of(FILE, 'return "small"', "set_on_computed") in covered
    for returned in ("str set", "list set"):
        assert line_of(FILE, f'return "{returned}"', "set_on_computed") not in covered
    # the forks on the changed list and on the str made from s, both still tracked after the
    # sets, are the ones the same target records without them
    forks = _forks(line)
    assert len(forks) == 2 and forks == _forks(first_line(untouched.stdout))
    assert _solved_covers(set_on.stdout, "set_on_computed", "big")
    assert _solved_covers(untouched.stdout, "computed_untouched", "big")


# the walk forks a range of `n` records for a seed of 2, taken while n holds another item
_WALK_OF_TWO = [[">", "n", 0], [">", "n", 1], [">", "n", 2]]
# each flip of a walk's end is a longer walk, so a run of one stops once no input gains a line
_PLATEAU = ("--plateau", "2")


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-on-a-range
def test_refuses_on_a_range() -> None:
    result = run_pyct(f"{TARGET}::set_on_a_range", '{"n": 2}', *_PLATEAU)

    assert result.returncode == 0, result.stderr
    # the fixture raises the messages it kept, one for each statement plain Python refused
    error = python_raise(lambda: attributes.set_on_a_range(2))
    assert isinstance(error, LookupError) and len(error.args[0]) == 3
    line = first_line(result.stdout)
    raised(line, error)
    assert [expression for expression, _ in _forks(line)] == _WALK_OF_TWO


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-on-a-dict-view
def test_refuses_on_a_dict_view() -> None:
    result = run_pyct(f"{TARGET}::set_on_views", '{"d": {"k": 1}}')

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: attributes.set_on_views({"k": 1}))
    assert isinstance(error, LookupError) and len(error.args[0]) == 6
    raised(first_line(result.stdout), error)


def _ran_cleanly(target: str, seed: str, *argv: str) -> tuple[str, dict[str, object]]:
    """Run the target, check it ended with no pyct failure, and hand back stdout and its line."""
    result = run_pyct(f"{TARGET}::{target}", seed, *argv)

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    return result.stdout, line


# refuse-an-attribute-a-plain-str-list-or-dict-refuses-refuses-a-name-pyct-keeps
@pytest.mark.parametrize(("seed", "plain"), SEEDS, ids=SEED_IDS)
def test_refuses_a_name_pyct_keeps(seed: str, plain: object) -> None:
    function = "set_pyct_s_names_on_a_sized"
    assert getattr(attributes, function)(plain) == "small"
    stdout, line = _ran_cleanly(function, seed)

    assert _forks(line) == [([">", ["len", "x"], 3], False)]
    assert _solved_covers(stdout, function, "big")


def test_refuses_a_name_pyct_keeps_on_a_range() -> None:
    assert attributes.set_pyct_s_names_on_a_range(2) == "walked"
    _, line = _ran_cleanly("set_pyct_s_names_on_a_range", '{"n": 2}', *_PLATEAU)

    assert [expression for expression, _ in _forks(line)] == _WALK_OF_TWO


def test_refuses_a_name_pyct_keeps_on_a_view() -> None:
    function = "set_pyct_s_names_on_a_view"
    assert getattr(attributes, function)({"k": 1}) == "held"
    stdout, line = _ran_cleanly(function, '{"d": {"k": 1}}')

    assert _forks(line) == [(["in", "'k'", "d"], True)]
    assert _solved_covers(stdout, function, "missing")
