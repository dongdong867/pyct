"""A turned path: the rest of its new sides go shallowest first, once per path.

A pick turns its path when its ask ran to the solver's limit, or when its input left the plan
and covered no new line; the run decides the second, so here ``turn`` stands for it
(fork-order-shallowest-first-after-a-leave-without-gain).
"""

from pyct.branches.tree import Tree
from pyct.core.branch import Branch, Site


def fork(line: int, *, taken: bool = True) -> Branch:
    """A fork on x at its own line, so the forks of a path are told apart."""
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def positions(tree: Tree) -> list[int]:
    """The positions of every pick left, in order."""
    return [picked.aim.position for picked in iter(tree.next, None)]


def test_a_turn_sends_the_rest_of_its_path_s_new_sides_shallowest_first() -> None:
    tree = Tree()
    tree.add(tuple(fork(line) for line in (2, 3, 4, 5)))
    first = tree.next()

    tree.turn()

    assert first is not None and first.aim.position == 3
    assert positions(tree) == [0, 1, 2]


def test_a_second_turn_on_a_path_keeps_it_shallowest_first() -> None:
    tree = Tree()
    tree.add(tuple(fork(line) for line in (2, 3, 4, 5)))
    tree.next()
    tree.turn()
    second = tree.next()

    tree.turn()

    assert second is not None and second.aim.position == 0
    assert positions(tree) == [1, 2]


def test_a_turn_after_a_timeout_on_the_same_path_keeps_it_shallowest_first() -> None:
    tree = Tree()
    tree.add(tuple(fork(line) for line in (2, 3, 4, 5)))
    tree.next()
    tree.timed_out()
    tree.next()

    tree.turn()

    assert positions(tree) == [1, 2]


def test_a_turn_leaves_a_later_path_deepest_first() -> None:
    tree = Tree()
    tree.add((fork(2), fork(3), fork(4)))
    tree.add((fork(6), fork(7), fork(8)))
    tree.next()

    tree.turn()
    aims = [(picked.path, picked.aim.position) for picked in iter(tree.next, None)]

    assert aims == [(0, 0), (0, 1), (1, 2), (1, 1), (1, 0)]


def test_a_turn_before_any_pick_changes_no_order() -> None:
    tree = Tree()
    tree.add((fork(2), fork(3)))

    tree.turn()

    assert positions(tree) == [1, 0]


def test_a_turn_sends_no_fork_at_its_site_last() -> None:
    tree = Tree()
    tree.add(tuple(fork(line) for line in (5, 9, 6, 9)))
    tree.next()

    tree.turn()

    # unlike a timeout, a turn alone leaves the other fork at line 9 among the new sides
    assert positions(tree) == [0, 1, 2]


def test_a_timeout_on_a_turned_path_still_sends_its_site_last() -> None:
    tree = Tree()
    tree.add(tuple(fork(line) for line in (2, 9, 9, 6, 4)))
    tree.next()
    tree.turn()
    tree.next()
    tree.next()

    tree.timed_out()

    # the fork at line 9 at position 2 waits for the last picks, behind line 6
    assert positions(tree) == [3, 2]
