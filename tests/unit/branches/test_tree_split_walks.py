"""A walk's forks over a split's list wait behind every other fork: decision
fork-order-a-split-s-walk-forks-after-the-path-s-other-forks."""

from pyct.branches.tree import Tree
from pyct.core.branch import Branch, Expression, Site
from pyct.results.record import Aim


def fork(line: int, *, taken: bool = True) -> Branch:
    """A fork on x at its own line."""
    return Branch(["<", "x", line], taken, Site(file="m.py", line=line, col=7))


def walk(line: int, *, taken: bool = True) -> Branch:
    """A walk's fork over a split's list at its own line."""
    expression: Expression = [">", ["len", ["splitlines", "s"]], line]
    return Branch(expression, taken, Site(file="m.py", line=line, col=3), split_walk=True)


def _lines(tree: Tree) -> list[int]:
    return [picked.aim.site.line for picked in iter(tree.next, None)]


def test_a_path_s_split_walks_come_after_its_other_forks() -> None:
    tree = Tree()
    # a loop over lines: a walk's fork, then the line's own fork, on each pass
    tree.add((walk(1), fork(2), walk(3), fork(4), walk(5, taken=False)))

    # the line forks, deepest first, then the walk's, deepest first
    assert _lines(tree) == [4, 2, 5, 3, 1]


def test_split_walks_wait_behind_every_path_s_other_forks_oldest_path_first() -> None:
    tree = Tree()
    tree.add((walk(1), fork(2), walk(3, taken=False)))
    tree.add((fork(10), walk(11, taken=False)))

    assert _lines(tree) == [2, 10, 3, 1, 11]


def test_a_fork_at_a_site_a_pick_timed_out_at_still_comes_before_a_split_walk() -> None:
    tree = Tree()
    tree.add((walk(1), fork(2), walk(3), fork(4), walk(5, taken=False)))

    first = tree.next()
    tree.timed_out()
    rest = _lines(tree)

    # line 4 timed out; line 2 waits for the last picks, and the walk's forks for after it
    assert first is not None and first.aim == Aim(site=fork(4).site, position=3)
    assert rest == [2, 5, 3, 1]


def test_a_path_whose_split_walks_are_open_is_kept_for_the_answers_that_extend_it() -> None:
    tree = Tree()
    tree.add((walk(1, taken=False),))
    tree.add((fork(2),))

    assert tree.oldest == 0
    assert _lines(tree) == [2, 1]
    assert tree.oldest == 2
