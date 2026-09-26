"""The cap on a printed expression: whole up to the limit, past it the top with cut parts."""

import time

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.jsonl import render
from pyct.results.printed import CUT, LIMIT, printed, printed_forks
from pyct.results.record import InputRecord


def _tree(nodes: int) -> Expression:
    """A balanced expression of exactly ``nodes`` nodes, shallow enough to walk by recursion."""
    if nodes == 1:
        return "x"
    if nodes == 2:
        return ["-", "x"]
    left = (nodes - 1) // 2
    return ["+", _tree(left), _tree(nodes - 1 - left)]


def _nodes(expression: Expression) -> int:
    """Nodes as a line prints them: a list and each of its operands, a cut part included."""
    if not isinstance(expression, list):
        return 1
    return 1 + sum(_nodes(part) for part in expression[1:])


def _stands_for(expression: Expression) -> int:
    """Nodes the printed expression stands for: a cut part counts as the N it carries."""
    if isinstance(expression, list) and expression[0] == CUT:
        count = expression[1]
        assert isinstance(count, int)
        return count
    if not isinstance(expression, list):
        return 1
    return 1 + sum(_stands_for(part) for part in expression[1:])


def _cuts(expression: Expression) -> list[Expression]:
    """Every cut part of a printed expression, left to right."""
    if not isinstance(expression, list):
        return []
    if expression[0] == CUT:
        return [expression]
    return [cut for part in expression[1:] for cut in _cuts(part)]


def test_an_expression_under_the_limit_is_printed_as_it_is() -> None:
    expression: Expression = ["==", "s", "'abc'"]

    assert printed(expression) is expression


def test_an_expression_exactly_at_the_limit_is_printed_whole() -> None:
    expression = _tree(LIMIT)

    assert _nodes(expression) == LIMIT
    assert printed(expression) is expression


def test_one_node_over_the_limit_cuts_a_part_and_keeps_the_top() -> None:
    expression = _tree(LIMIT + 1)

    written = printed(expression)

    assert isinstance(written, list) and written[0] == "+"
    assert _nodes(written) <= LIMIT
    assert len(_cuts(written)) >= 1
    # the cut parts stand for exactly what they replace, so nothing is lost from the count
    assert _stands_for(written) == LIMIT + 1


def test_a_large_expression_cuts_several_parts_the_same_way_every_time() -> None:
    expression = _tree(20 * LIMIT)

    written = printed(expression)

    assert _nodes(written) <= LIMIT
    assert len(_cuts(written)) > 1
    assert _stands_for(written) == 20 * LIMIT
    assert printed(expression) == written


def test_the_top_operator_and_small_operands_are_kept() -> None:
    expression = ["==", _tree(5 * LIMIT), "'abc'"]

    written = printed(expression)

    assert isinstance(written, list)
    assert (written[0], written[2]) == ("==", "'abc'")
    assert _nodes(written) <= LIMIT


def _rebuilt(passes: int) -> tuple[Expression, int]:
    """`s = s[:1] + s[2:]` run ``passes`` times: each pass holds the last one twice.

    The expression shares the old one where Python shares it, so it is small
    in memory; written out in full it doubles with each pass. The count is
    the written-out size, worked out without writing it.
    """
    term: Expression = "s"
    size = 1
    for _ in range(passes):
        term = ["+", ["[:]", term, None, 1], ["[:]", term, 2, None]]
        size = 1 + 2 * (size + 3)
    return term, size


def _distinct(expression: Expression) -> int:
    """Distinct nodes of an expression: each list once, however often it is reached, with its
    leaves, and a leaf on its own is one."""
    if not isinstance(expression, list):
        return 1
    nodes, seen, stack = 0, set(), [expression]
    while stack:
        part = stack.pop()
        if id(part) not in seen:
            seen.add(id(part))
            lists = [operand for operand in part[1:] if isinstance(operand, list)]
            nodes += len(part) - len(lists)
            stack.extend(lists)
    return nodes


def _cut_from(written: Expression, expression: Expression) -> list[tuple[int, Expression]]:
    """Each cut part's N, beside the part of the expression it stands in for."""
    found: list[tuple[int, Expression]] = []
    stack = [(written, expression)]
    while stack:
        shown, part = stack.pop()
        if isinstance(shown, list) and shown[0] == CUT:
            count = shown[1]
            assert isinstance(count, int)
            found.append((count, part))
        elif isinstance(shown, list):
            assert isinstance(part, list) and shown[0] == part[0]
            stack.extend(zip(shown[1:], part[1:], strict=True))
    return found


def test_a_shared_expression_is_counted_and_cut_without_writing_it_out() -> None:
    expression, size = _rebuilt(300)
    condition: Expression = ["==", expression, "'abc'"]

    start = time.perf_counter()
    written = printed(condition)
    spent = time.perf_counter() - start

    # written out, the expression would hold about 2 ** 302 nodes; each pass adds 7 of its own
    assert size > 2**300
    assert _nodes(written) <= LIMIT
    cuts = _cut_from(written, condition)
    assert cuts
    # a cut part counts each node it reaches once, however often it reaches it
    assert all(count == _distinct(part) for count, part in cuts)
    assert max(count for count, _ in cuts) < 7 * 300 + 2
    assert spent < 1.0


def test_forks_that_share_their_parts_are_each_printed_as_it_prints_alone() -> None:
    # each pass's fork holds the string every pass before it built
    term: Expression = "s"
    forks: list[Branch] = []
    for i in range(40):
        forks.append(
            Branch(expression=[">", ["len", term], i], taken=True, site=Site("m.py", 5, 7))
        )
        term = ["+", ["[:]", term, None, i], ["[:]", term, i + 1, None]]

    written = printed_forks(forks)

    assert written == tuple(printed(fork.expression) for fork in forks)
    assert any(_cuts(expression) for expression in written)


def _edit_loop(passes: int) -> list[Branch]:
    """`s = s[:i] + s[i] + s[i+1:]` for each i, each pass forking on `len(s) > i`, then `s == …`.

    Each pass holds the last pass's string three times, so written out the
    condition triples on every pass, while each pass adds ten nodes of its own.
    """
    term: Expression = "s"
    forks: list[Branch] = []
    for i in range(passes):
        forks.append(
            Branch(expression=[">", ["len", term], i], taken=True, site=Site("m.py", 5, 7))
        )
        term = ["+", ["+", ["[:]", term, None, i], ["[]", term, i]], ["[:]", term, i + 1, None]]
    forks.append(Branch(expression=["==", term, "'abc'"], taken=False, site=Site("m.py", 7, 7)))
    return forks


def test_a_thousand_passes_of_the_edit_loop_cut_to_a_short_line() -> None:
    forks = _edit_loop(1000)

    written = printed_forks(forks)

    # written out, the last condition holds about 3 ** 1000 nodes; each cut part says how many
    # distinct nodes it holds, which is about ten for each pass that built it
    pairs = zip(written, forks, strict=True)
    counts = [count for shown, fork in pairs for count, _ in _cut_from(shown, fork.expression)]
    assert counts
    assert all(2 < count < 10_000 for count in counts)
    # the stdout line of an input whose one fork is the loop's last condition
    record = InputRecord(args={"s": "a" * 1000}, forks=(forks[-1],), covered_lines=frozenset({5}))
    coverage = Coverage(covered={"m.py": frozenset({5})}, lines={"m.py": frozenset({5, 7})})
    assert len(render(record, coverage).encode()) < 1_000_000
