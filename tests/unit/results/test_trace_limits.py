"""The fork line past the printer's limits: a cut expression, a condition nested past Python's
recursion limit, and a string built over many passes."""

import re

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.printed import LIMIT
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace

COVERAGE = Coverage(covered={"m.py": frozenset({5})}, lines={"m.py": frozenset({5})})


def test_render_trace_writes_an_expression_past_the_cap_cut() -> None:
    term: Expression = "s"
    for _ in range(40):
        term = ["+", ["[:]", term, None, 1], ["[:]", term, 2, None]]
    fork = Branch(expression=["==", term, "'abc'"], taken=False, site=Site("m.py", 5, 7))
    record = InputRecord(args={"s": "abc"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # the fork line holds what the stdout line holds, each cut part as the distinct nodes it holds
    assert lines[1].startswith("fork m.py:5:7  (")
    assert lines[1].endswith(" == 'abc'  not taken")
    assert " nodes)" in lines[1]
    assert len(lines[1]) < 20_000


def test_render_trace_writes_a_condition_nested_past_the_recursion_limit() -> None:
    term: Expression = "x"
    for _ in range(LIMIT - 1):
        term = ["abs", term]
    # LIMIT nodes, so the line prints it whole, nested deeper than Python's recursion limit
    fork = Branch(expression=term, taken=True, site=Site("m.py", 5, 7))
    record = InputRecord(args={"x": 1}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    nested = LIMIT - 1
    assert lines[1] == f"fork m.py:5:7  {'abs(' * nested}x{')' * nested}  taken"


def test_render_trace_writes_a_string_built_over_five_thousand_passes() -> None:
    term: Expression = "s"
    for _ in range(5000):
        term = ["+", term, "' '"]
    fork = Branch(expression=["startswith", term, "'ok'"], taken=False, site=Site("m.py", 5, 7))
    record = InputRecord(args={"s": "a"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # the top of the string is kept over the cut part, each pass one more sum, as Python reads a
    # chain of them from the left
    assert re.fullmatch(
        r"fork m\.py:5:7  \(\.\.\.\(\d+ nodes\)( \+ ' ')+\)\.startswith\('ok'\)  not taken",
        lines[1],
    )
