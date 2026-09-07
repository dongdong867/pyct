import json

from pyct.results.coverage import Coverage
from pyct.results.jsonl import render
from pyct.results.record import InputRecord


def test_render_is_one_json_line_with_sorted_lines() -> None:
    record = InputRecord(args={"x": 1}, covered_lines=frozenset({6, 5}))
    coverage = Coverage(covered={"m.py": frozenset({6, 5})}, total={"m.py": 7})

    line = render(record, coverage)

    assert "\n" not in line
    assert json.loads(line) == {"args": {"x": 1}, "covered": {"m.py": [5, 6]}, "total": {"m.py": 7}}
