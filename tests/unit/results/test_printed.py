"""The cap on a printed expression: whole up to the limit, past it the top with cut parts."""

import random
import time
import tracemalloc

import pytest

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


def _counts_from(
    written: Expression, expression: Expression
) -> list[tuple[int | None, Expression]]:
    """Each cut part's N, None where it was left uncounted, beside the part it stands in for."""
    found: list[tuple[int | None, Expression]] = []
    stack = [(written, expression)]
    while stack:
        shown, part = stack.pop()
        if isinstance(shown, list) and shown[0] == CUT:
            count = shown[1]
            assert count is None or isinstance(count, int)
            found.append((count, part))
        elif isinstance(shown, list):
            assert isinstance(part, list) and shown[0] == part[0]
            stack.extend(zip(shown[1:], part[1:], strict=True))
    return found


def _cut_from(written: Expression, expression: Expression) -> list[tuple[int, Expression]]:
    """Each cut part's N, beside the part of the expression it stands in for, every one counted."""
    found: list[tuple[int, Expression]] = []
    for count, part in _counts_from(written, expression):
        assert isinstance(count, int)
        found.append((count, part))
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


def test_a_list_reached_through_two_operands_is_counted_once() -> None:
    # the last operand reaches `first`, `early`, a long chain and `shared`, numbered in that
    # order; the ones before it reach `early` and `shared` again, far apart, and are joined first
    first: Expression = ["j", "z"]
    early: Expression = ["k", "z"]
    chain: Expression = ["-", "w"]
    for _ in range(100):
        chain = ["-", chain]
    shared: Expression = ["g", "y"]
    pads: list[Expression] = [["p", "a", "b"] for _ in range(LIMIT // 2)]
    expression: Expression = [
        "top",
        *pads,
        ["h", early, shared],
        ["f", shared, chain, early, first],
    ]

    written = printed(expression)

    # too many operands to open within the limit, so the whole expression is one cut part
    assert written == [CUT, _distinct(expression)]


def test_an_access_to_a_value_inside_an_argument_is_written_whole() -> None:
    access: Expression = "config"
    for _ in range(2000):
        access = ["[]", access, "'a'"]
    wide = _tree(2 * LIMIT)
    fork = Branch(expression=["==", ["+", access, 1], wide], taken=True, site=Site("m.py", 5, 7))

    (written,) = printed_forks([fork], lambda part: part is access)

    # the access is the name the line's args find the value by, one node however deep, and the
    # line cuts the rest of the condition around it
    assert isinstance(written, list) and isinstance(written[1], list)
    assert written[1][1] is access
    assert _cut_from(written[2], wide)


def test_a_cut_part_that_holds_an_access_counts_it_as_one_node() -> None:
    # `s = order["name"]`, then `s = s + "x"` over 600 passes: every cut part reaches the access
    access: Expression = ["[]", "order", "'name'"]
    term: Expression = access
    for _ in range(600):
        term = ["+", term, "'x'"]
    fork = Branch(expression=["==", term, "'q'"], taken=False, site=Site("m.py", 5, 7))

    (written,) = printed_forks([fork], lambda part: part is access)

    # a part k passes deep holds k `+` nodes, k `'x'` leaves and the access, one node however
    # many steps it takes
    cuts = _cut_from(written, fork.expression)
    assert cuts
    for count, part in cuts:
        passes = 0
        while part is not access:
            assert isinstance(part, list)
            part, passes = part[1], passes + 1
        assert count == 2 * passes + 1


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


def test_counting_cut_short_leaves_a_count_out_rather_than_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the loop's last fork, whose cut parts reach every pass: counting them all takes 396 steps
    forks = _edit_loop(12)[-1:]
    exact: dict[int, int] = {}
    wrong: list[tuple[int, int]] = []
    cut_short = 0

    # every limit up to what the whole count needs, so the steps run out at every point of it,
    # inside a join and between two
    for limit in range(400):
        monkeypatch.setattr("pyct.results.printed.COUNTING_STEPS", limit)
        counts = [
            pair
            for shown, fork in zip(printed_forks(forks), forks, strict=True)
            for pair in _counts_from(shown, fork.expression)
        ]
        cut_short += any(count is None for count, _ in counts)
        wrong += [
            (limit, count)
            for count, part in counts
            if count is not None and count != exact.setdefault(id(part), _distinct(part))
        ]

    # a part the steps ran out on has no count, never a part of one
    assert wrong == []
    assert 0 < cut_short < 400


# the string a gathering loop takes its pieces of: a parameter, and a string the target made
GATHERED_FROM: dict[str, Expression] = {"s": "s", "s[1:]": ["[:]", "s", 1, None]}


def _gathered(characters: int, string: Expression) -> list[Branch]:
    """`c = u[i]`, then `if c == "x":`, then `t = t + c`, for each i, and a last fork on t.

    Each piece is held by its own fork and by t, so the count of each waits
    until the last fork's walk reads it. Every piece, and every length fork,
    holds the one string u.
    """
    term: Expression = "''"
    forks: list[Branch] = []
    for i in range(characters):
        piece: Expression = ["[]", string, i]
        forks.append(
            Branch(expression=[">", ["len", string], i], taken=True, site=Site("m.py", 2, 7))
        )
        forks.append(Branch(expression=["==", piece, "'x'"], taken=False, site=Site("m.py", 3, 7)))
        term = ["+", term, piece]
    forks.append(Branch(expression=["==", term, "'abc'"], taken=False, site=Site("m.py", 5, 7)))
    return forks


@pytest.mark.parametrize("string", GATHERED_FROM.values(), ids=list(GATHERED_FROM))
def test_gathered_pieces_count_each_node_they_reach_once(string: Expression) -> None:
    forks = _gathered(300, string)

    written = printed_forks(forks)[-1]

    # the gathered string reaches each piece, and each piece the one string it was taken of
    cuts = _cut_from(written, forks[-1].expression)
    assert cuts
    assert all(count == _distinct(part) for count, part in cuts)


@pytest.mark.parametrize("string", GATHERED_FROM.values(), ids=list(GATHERED_FROM))
def test_gathered_pieces_that_wait_below_the_cut_are_counted_in_little_memory(
    string: Expression,
) -> None:
    # the last fork alone: the count walks below the part it cuts, where every piece is
    # numbered before the gathered strings that hold it, and waits for one of them to read it
    forks = _gathered(10_000, string)[-1:]

    tracemalloc.start()
    try:
        printed_forks(forks)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # what a waiting piece reaches is kept as runs of the numbers it holds, its own nodes and the
    # string's, so the memory grows with the pieces, about 7.6 MB here. Kept from the walk's
    # first number, it grew with their square, 25 MB here for pieces of s. Kept from its own
    # lowest number, it still did for pieces of s[1:], whose one list is numbered first, 19 MB
    assert peak < 12_000_000


def _compared_then_gathered(characters: int, compares: int) -> list[Branch]:
    """`c = s[i]`, compared with ``compares`` more letters after `"x"`, then `t = t + c`, for
    each i, and a last fork on t: an escaper, or a tokenizer, that gathers what it read.

    In a walk of every fork, each piece's compares sit between it and the next piece.
    """
    term: Expression = "''"
    forks: list[Branch] = []
    for i in range(characters):
        piece: Expression = ["[]", "s", i]
        forks.append(Branch(expression=[">", ["len", "s"], i], taken=True, site=Site("m.py", 2, 7)))
        letters = ["'x'", *(repr(chr(97 + k % 26) * (1 + k // 26)) for k in range(compares))]
        forks += [
            Branch(expression=["==", piece, letter], taken=False, site=Site("m.py", 3, 7))
            for letter in letters
        ]
        term = ["+", term, piece]
    forks.append(Branch(expression=["==", term, "'abc'"], taken=False, site=Site("m.py", 5, 7)))
    return forks


def test_pieces_compared_many_times_then_gathered_are_counted_quickly() -> None:
    forks = _compared_then_gathered(16_000, 30)

    start = time.perf_counter()
    written = printed_forks(forks)
    spent = time.perf_counter() - start

    # counted only below the part the last fork cuts, where the pieces sit side by side, in about
    # 1 s, or 3 s under coverage; counted over every fork, the compares between the pieces made
    # each join walk every piece before it, which took 30 s here
    cuts = _cut_from(written[-1], forks[-1].expression)
    assert cuts
    assert all(count == _distinct(part) for count, part in cuts)
    assert spent < 15.0


def _joined_strings(pieces: list[Expression]) -> Expression:
    """The pieces joined in order into one string, starting from an empty one."""
    term: Expression = "''"
    for piece in pieces:
        term = ["+", term, piece]
    return term


def _orthogonal_vectors(vectors: int, width: int, forks: int) -> list[Branch]:
    """Orthogonal vectors as strings: b_j is s[j], each of ``width`` columns joins the b_j with
    its bit set, and each a_i joins the columns of its own bits. Each fork tests a sum of its
    share of the a_i, so the a_i are what the line cuts.

    What an a_i reaches holds every b_j not orthogonal to it, so counting each exactly is as
    hard as finding two orthogonal vectors.
    """
    rng = random.Random(0)
    pieces: list[Expression] = [["[]", "s", j] for j in range(vectors)]
    columns = [
        _joined_strings([piece for piece in pieces if rng.random() < 0.5]) for _ in range(width)
    ]
    shown: list[Branch] = []
    for _ in range(forks):
        parts: list[Expression] = [
            _joined_strings([c for c in columns if rng.random() < 0.5])
            for _ in range(vectors // forks)
        ]
        while len(parts) > 1:
            parts = [
                ["+", *parts[i : i + 2]] if i + 1 < len(parts) else parts[i]
                for i in range(0, len(parts), 2)
            ]
        shown.append(
            Branch(expression=["==", parts[0], "'x'"], taken=False, site=Site("m.py", 3, 7))
        )
    return shown


def test_counting_the_orthogonal_vectors_shape_stops_at_its_limit() -> None:
    forks = _orthogonal_vectors(2048, 40, 4)

    start = time.perf_counter()
    written = printed_forks(forks)
    spent = time.perf_counter() - start

    # the count stops at its limit of steps: the parts it counted are exact, and the rest print
    # no count, so the line still takes a bounded time, about 0.5 s, or 1.5 s under coverage
    counts = [
        pair
        for shown, fork in zip(written, forks, strict=True)
        for pair in _counts_from(shown, fork.expression)
    ]
    counted = [(count, part) for count, part in counts if count is not None]
    assert counted and len(counted) < len(counts)
    assert all(count == _distinct(part) for count, part in counted[:10])
    assert spent < 10.0
