from pyct.results.record import InputRecord
from pyct.results.trace import render_trace
from tests.unit.results.test_trace import COVERAGE, FORK


def test_render_trace_names_where_a_seed_came_from_after_its_source() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({6, 5}))

    text = render_trace(record, COVERAGE, label="seeds.jsonl:3")

    assert text.splitlines()[0] == 'seed seeds.jsonl:3 {"x": 1}'
