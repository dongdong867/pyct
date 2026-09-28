"""Acceptance tests for the refuse-a-tracked-dict-view-s-pickle-as-python-does bug.

A tracked dict's `keys()`, `values()` and `items()` refuse a pickle at every protocol, a copy and
a deep copy with the error plain Python raises for its own view, and record nothing. Each test
runs pyct through the command line and reads plain Python's error from the same fixture called
on a plain dict in this test run, since Python's words differ between releases.
"""

import pytest

from targets.types import views
from tests.acceptance.harness import first_line, run_pyct
from tests.acceptance.test_read_a_dict_view_s_type_as_python_s import FILE, PLAIN, SEED, TARGET
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    covers_plainly,
    python_raise,
    raised,
)


# refuse-a-tracked-dict-view-s-pickle-as-python-does-refuses-each-pickle
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_refuses_each_pickle(where: tuple[str, ...]) -> None:
    assert views.pickled(PLAIN) == "same"
    covers_plainly(f"{TARGET}::pickled", SEED, FILE, "same", *where)


# refuse-a-tracked-dict-view-s-pickle-as-python-does-refuses-each-copy
def test_refuses_each_copy() -> None:
    assert views.copied(PLAIN) == "same"
    covers_plainly(f"{TARGET}::copied", SEED, FILE, "same")


# refuse-a-tracked-dict-view-s-pickle-as-python-does-reports-python-s-words
def test_reports_python_s_words() -> None:
    result = run_pyct(f"{TARGET}::dumped", SEED)

    assert result.returncode == 0, result.stderr
    error = python_raise(lambda: views.dumped(PLAIN))
    assert isinstance(error, TypeError)
    raised(first_line(result.stdout), error)
