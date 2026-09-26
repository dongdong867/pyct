"""The cap on a printed expression: whole up to the limit, past it the top with cut parts."""

import time

from pyct.core.branch import Branch, Expression, Site
from pyct.results.printed import CUT, LIMIT, printed, printed_forks


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


def test_a_shared_expression_is_counted_and_cut_without_writing_it_out() -> None:
    expression, size = _rebuilt(300)

    start = time.perf_counter()
    written = printed(["==", expression, "'abc'"])
    spent = time.perf_counter() - start

    # written out, the expression would hold about 2 ** 302 nodes
    assert size > 2**300
    assert _nodes(written) <= LIMIT
    assert _stands_for(written) == 1 + size + 1
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
