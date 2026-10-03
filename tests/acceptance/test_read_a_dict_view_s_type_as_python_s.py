"""Acceptance tests for the read-a-dict-view-s-type-as-python-s bug.

A tracked dict's `keys()`, `values()` and `items()` read as Python's view types: a call written
`type(v)` in the target's package, `v.__class__` and `isinstance` answer as for a plain dict's
view, and what the view records stays as it was. Each test runs pyct through the command line and
reads plain Python's answer from the same fixture called on a plain dict in this test run.
"""

import pytest

from targets.types import views
from tests.acceptance.harness import REPO_ROOT, first_line, forks_of, input_lines, run_pyct
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    covers_plainly,
    line_of,
)

TARGET = "targets.types.views"
FILE = REPO_ROOT / "targets" / "types" / "views.py"
SEED = '{"d": {"k": 1}}'
PLAIN = {"k": 1}


# read-a-dict-view-s-type-as-python-s-reads-each-view-s-type
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_reads_each_view_s_type(where: tuple[str, ...]) -> None:
    assert views.each_type(PLAIN) == "base"
    line = covers_plainly(f"{TARGET}::each_type", SEED, FILE, "base", *where)
    assert line_of(FILE, 'return "other"', "each_type") not in covered_in(line, str(FILE))


# read-a-dict-view-s-type-as-python-s-follows-past-a-type-guard
def test_follows_past_a_type_guard() -> None:
    assert views.guarded(PLAIN) == "missing" and views.guarded({"a": 1}) == "found"
    result = run_pyct(f"{TARGET}::guarded", SEED)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (["in", "'a'", "d"], False)
    ]
    assert seed["downgrades"] == []
    solved = input_lines(result.stdout)[1]
    arguments = solved["args"]
    assert isinstance(arguments, dict) and "a" in arguments["d"]
    assert line_of(FILE, 'return "found"', "guarded") in covered_in(solved, str(FILE))


# read-a-dict-view-s-type-as-python-s-refuses-a-view-built-through-its-type
def test_refuses_a_view_built_through_its_type() -> None:
    result = run_pyct(f"{TARGET}::built", SEED)

    assert result.returncode == 0, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    covered = covered_in(line, str(FILE))
    assert line_of(FILE, 'return "same"', "built") in covered
    assert line_of(FILE, 'return "differs"', "built") not in covered
