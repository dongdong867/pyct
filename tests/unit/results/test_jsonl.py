import json

from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render
from pyct.results.record import InputRecord

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))
COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, total={"m.py": 7})


def test_render_is_one_json_line_with_sorted_lines() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({6, 5}))

    line = render(record, COVERAGE)

    assert "\n" not in line
    assert json.loads(line) == {
        "args": {"x": 1},
        "forks": [],
        "covered": {"m.py": [5, 6]},
        "total": {"m.py": 7},
        "failure": None,
        "downgrades": [],
    }


def test_render_writes_each_fork_with_its_site_and_expression() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert payload["forks"] == [
        {"file": "m.py", "line": 5, "col": 7, "taken": True, "expression": ["<", "x", 10]}
    ]


def test_render_puts_the_forks_between_the_args_and_the_coverage() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert list(payload) == ["args", "forks", "covered", "total", "failure", "downgrades"]


def test_render_keeps_the_forks_in_execution_order() -> None:
    second = Branch(expression="y", taken=False, site=Site(file="m.py", line=9, col=3))
    record = InputRecord(args={"x": 1}, forks=(FORK, second), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert [fork["line"] for fork in payload["forks"]] == [5, 9]


def test_render_writes_the_failure_as_its_kind_and_detail() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    payload = json.loads(render(record, COVERAGE))

    assert payload["failure"] == {"kind": "target_raised", "detail": "ValueError: too small"}


def test_render_lists_the_downgrades_in_order() -> None:
    record = InputRecord(
        args={"x": 1}, forks=(), covered_lines=frozenset(), downgrades=("__abs__", "__add__")
    )

    payload = json.loads(render(record, COVERAGE))

    assert payload["downgrades"] == ["__abs__", "__add__"]
