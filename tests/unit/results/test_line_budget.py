"""The line's budget: its forks' expressions print whole in order while they fit, then cut."""

import time

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.printed import CUT, LIMIT, LINE_LIMIT, printed, printed_forks
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace
from tests.unit.results.test_printed import _nodes, _tree

COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, lines={"m.py": frozenset(range(1, 8))})


def _countdown(passes: int) -> list[Branch]:
    """`while x > 0: x -= 1` from x = passes: fork i holds every pass before it, 2i + 3 nodes."""
    value: Expression = "x"
    forks: list[Branch] = []
    for i in range(passes + 1):
        forks.append(Branch(expression=[">", value, 0], taken=i < passes, site=Site("m.py", 2, 10)))
        value = ["-", value, 1]
    return forks


def _count(expression: Expression) -> Expression:
    """The N a fork cut whole carries."""
    assert isinstance(expression, list) and expression[0] == CUT
    return expression[1]


def test_forks_within_the_line_budget_print_as_each_prints_alone() -> None:
    # forks 0 to 314 hold 99,855 nodes between them
    forks = _countdown(314)

    shown = printed_forks(forks)

    assert shown.cut_from is None
    assert all(a is fork.expression for a, fork in zip(shown.expressions, forks, strict=True))
    assert sum(_nodes(expression) for expression in shown.expressions) == 99_855


def test_forks_past_the_line_budget_print_one_cut_part_each() -> None:
    forks = _countdown(400)

    shown = printed_forks(forks)

    # fork 315 holds 633 nodes, which would take the line to 100,488
    assert shown.cut_from == 315
    assert all(
        a is fork.expression for a, fork in zip(shown.expressions[:315], forks, strict=False)
    )
    assert list(shown.expressions[315:]) == [[CUT, 2 * i + 3] for i in range(315, 401)]


@pytest.mark.parametrize(
    ("last", "cut_from"),
    [
        # 99,855 nodes and 144 leaves, then one more leaf: 100,000, which fills the line
        ("y", None),
        # the same, then a fork of two nodes: 100,001
        (["-", "y"], 459),
    ],
    ids=["fills the line", "one node past it"],
)
def test_the_line_keeps_a_fork_that_fills_it_and_cuts_the_one_past(
    last: Expression, cut_from: int | None
) -> None:
    leaves = [Branch(expression="y", taken=True, site=Site("m.py", 7, 3))] * 144
    forks = [
        *_countdown(314),
        *leaves,
        Branch(expression=last, taken=True, site=Site("m.py", 8, 3)),
    ]

    shown = printed_forks(forks)

    # 99,855 nodes, then 144 leaves: 99,999, and the last fork one node or two
    assert sum(_nodes(expression) for expression in shown.expressions[:459]) == 99_999
    assert shown.cut_from == cut_from
    assert shown.expressions[-1] == (last if cut_from is None else [CUT, 2])


def test_a_fork_cut_to_the_cap_counts_what_it_prints_against_the_line() -> None:
    wide = [Branch(expression=_tree(2 * LIMIT), taken=True, site=Site("m.py", 5, 7))] * 200

    shown = printed_forks(wide)

    # each prints its cut top, no more than the cap, and the line keeps as many as fit whole
    each = _nodes(printed(wide[0].expression))
    assert each <= LIMIT
    assert shown.cut_from == LINE_LIMIT // each
    assert list(shown.expressions[: shown.cut_from]) == [printed(wide[0].expression)] * (
        LINE_LIMIT // each
    )


def test_a_leaf_or_an_access_past_the_line_budget_is_one_cut_node() -> None:
    access: Expression = ["[]", "items", 0]
    forks = [
        *_countdown(315),
        Branch(expression="b", taken=True, site=Site("m.py", 7, 3)),
        Branch(expression=access, taken=True, site=Site("m.py", 8, 3)),
    ]

    shown = printed_forks(forks, lambda part: part is access)

    assert shown.expressions[-2:] == ([CUT, 1], [CUT, 1])


def test_forks_past_the_line_budget_are_counted_within_the_line_s_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pyct.results.printed.COUNTING_STEPS", 16_000)
    forks = _countdown(2_000)

    counts = [_count(expression) for expression in printed_forks(forks).expressions[315:]]

    # counted in path order until the steps run out, each count exact, and the rest left out
    counted = [count for count in counts if count is not None]
    assert 0 < len(counted) < len(counts)
    assert counts == [2 * i + 3 for i in range(315, 315 + len(counted))] + [None] * (
        len(counts) - len(counted)
    )


def test_a_hundred_thousand_forks_print_in_a_bounded_time() -> None:
    forks = _countdown(100_000)

    start = time.perf_counter()
    shown = printed_forks(forks)
    spent = time.perf_counter() - start

    # about 0.3 s, most of it counting within the line's steps
    assert shown.cut_from == 315
    assert spent < 5.0


def test_render_trace_says_which_forks_the_line_cut_whole_after_the_last_fork() -> None:
    # fork i holds 2i + 3 nodes, so forks 0 to 314 hold 99,855 and fork 315 would pass the line's
    # budget
    record = InputRecord(
        args={"x": 320}, forks=tuple(_countdown(320)), covered_lines=frozenset({5})
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[315] == "fork m.py:2:10  x" + " - 1" * 314 + " > 0  taken"
    assert lines[316] == f"fork m.py:2:10  ...({2 * 315 + 3} nodes)  taken"
    assert lines[321] == f"fork m.py:2:10  ...({2 * 320 + 3} nodes)  not taken"
    assert lines[322:324] == [
        f"cut the expressions of 6 forks, from position 315 on, past the line's {LINE_LIMIT:,}"
        " nodes",
        "covered 2 of 7 lines in m.py",
    ]


def test_render_trace_says_nothing_cut_for_a_line_within_its_budget() -> None:
    record = InputRecord(
        args={"x": 314}, forks=tuple(_countdown(314)), covered_lines=frozenset({5})
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[316] == "covered 2 of 7 lines in m.py"
    assert not any(line.startswith("cut ") for line in lines)


def test_render_trace_writes_a_fork_cut_whole_and_left_uncounted_with_a_question_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pyct.results.printed.COUNTING_STEPS", 0)
    record = InputRecord(
        args={"x": 316}, forks=tuple(_countdown(316)), covered_lines=frozenset({5})
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[316:318] == [
        "fork m.py:2:10  ...(? nodes)  taken",
        "fork m.py:2:10  ...(? nodes)  not taken",
    ]
