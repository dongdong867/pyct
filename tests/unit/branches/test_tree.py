import time

import pytest

from pyct.branches.tree import ForkKey, Tree
from pyct.core.branch import Branch, Fact, Site
from pyct.results.record import Aim


def fork(line: int, *, taken: bool) -> Branch:
    """A fork on x at its own line, so the forks of a path are told apart."""
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def test_an_empty_tree_has_nothing_to_aim_at() -> None:
    assert Tree().next() is None


def test_a_path_with_no_fork_leaves_nothing_to_aim_at() -> None:
    tree = Tree()
    tree.add(())

    assert tree.next() is None


def test_the_deepest_fork_of_the_oldest_path_comes_first() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))
    tree.add((fork(4, taken=True), fork(5, taken=True)))

    picked = tree.next()

    assert picked is not None
    assert picked.prefix == (fork(2, taken=True), fork(3, taken=False))
    assert picked.aim == Aim(site=fork(3, taken=True).site, position=1)


def test_a_newer_path_waits_until_every_older_fork_was_aimed_at() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))
    tree.add((fork(4, taken=True), fork(5, taken=True)))

    picks = list(iter(tree.next, None))

    assert [picked.aim for picked in picks] == [
        Aim(site=fork(3, taken=True).site, position=1),
        Aim(site=fork(2, taken=True).site, position=0),
        Aim(site=fork(5, taken=True).site, position=1),
        Aim(site=fork(4, taken=True).site, position=0),
    ]
    # each pick names the path it extends, whose input an answer starts from
    assert [picked.path for picked in picks] == [0, 0, 1, 1]


def test_a_fork_whose_other_side_no_input_took_comes_before_the_loop() -> None:
    """The loop's case: both sides of the loop's test ran, so the fork before it comes first."""
    tree = Tree()
    tree.add((fork(2, taken=False), fork(3, taken=True), fork(3, taken=False)))
    first = tree.next()
    tree.add((fork(2, taken=False), fork(3, taken=True), fork(3, taken=True), fork(3, taken=False)))

    later = [picked.aim.position for picked in iter(tree.next, None)]

    assert first is not None and first.aim.position == 0
    # then the oldest path's open forks, deepest first, and the newer path's own fork
    assert later == [1, 3]


def test_a_long_loop_in_the_seed_waits_behind_the_fork_before_it() -> None:
    """`if y > 100:` before 200 passes of `while x > 0:`: the second input flips y."""
    tree = Tree()
    passes = tuple(fork(4, taken=True) for _ in range(200))
    tree.add((fork(2, taken=False), *passes, fork(4, taken=False)))

    picked = tree.next()

    assert picked is not None
    assert picked.aim == Aim(site=fork(2, taken=False).site, position=0)
    assert picked.prefix == (fork(2, taken=True),)


def test_a_seed_whose_every_side_ran_flips_its_last_fork() -> None:
    tree = Tree()
    tree.add((fork(4, taken=True), fork(4, taken=True), fork(4, taken=False)))

    picked = tree.next()

    assert picked is not None
    assert picked.aim == Aim(site=fork(4, taken=False).site, position=2)


def test_a_new_side_another_input_took_since_waits_its_turn() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))
    # line 3 goes the other way on another path, so line 3's other side is no longer new
    tree.add((fork(5, taken=True), fork(3, taken=False)))

    aims = [(picked.aim.site.line, picked.aim.position) for picked in iter(tree.next, None)]

    # the new sides first, oldest path first; then the rest, oldest path and deepest first
    assert aims == [(2, 0), (5, 0), (3, 1), (3, 1)]


def test_a_timeout_sends_the_rest_of_its_path_s_new_sides_shallowest_first() -> None:
    tree = Tree()
    tree.add(tuple(fork(line, taken=True) for line in (2, 3, 4, 5)))
    first = tree.next()

    tree.timed_out()
    later = [picked.aim.position for picked in iter(tree.next, None)]

    assert first is not None and first.aim.position == 3
    assert later == [0, 1, 2]


def test_a_second_timeout_on_a_path_keeps_it_shallowest_first() -> None:
    tree = Tree()
    tree.add(tuple(fork(line, taken=True) for line in (2, 3, 4, 5)))
    tree.next()
    tree.timed_out()
    second = tree.next()

    tree.timed_out()
    later = [picked.aim.position for picked in iter(tree.next, None)]

    assert second is not None and second.aim.position == 0
    assert later == [1, 2]


def test_a_timeout_leaves_a_later_path_deepest_first() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True), fork(4, taken=True)))
    tree.add((fork(6, taken=True), fork(7, taken=True), fork(8, taken=True)))
    tree.next()

    tree.timed_out()
    aims = [(picked.aim.site.line, picked.aim.position) for picked in iter(tree.next, None)]

    assert aims == [(2, 0), (3, 1), (8, 2), (7, 1), (6, 0)]


def test_a_timeout_before_any_pick_changes_no_order() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))

    tree.timed_out()
    aims = [picked.aim.position for picked in iter(tree.next, None)]

    assert aims == [1, 0]


def test_a_timeout_sends_every_other_fork_at_its_site_last() -> None:
    """The helper's case: `int(s)` after `s.isdigit()` forks at one site on each call."""
    tree = Tree()
    tree.add(tuple(fork(line, taken=True) for line in (5, 9, 6, 9)))
    first = tree.next()

    tree.timed_out()
    later = [picked.aim.position for picked in iter(tree.next, None)]

    assert first is not None and first.aim.position == 3
    # the new sides shallowest first, but for the one at the site that timed out, which is last
    assert later == [0, 2, 1]


def test_a_timeout_sends_a_fork_at_its_site_on_a_later_path_last() -> None:
    tree = Tree()
    tree.add((fork(5, taken=True), fork(9, taken=True)))
    tree.next()
    tree.timed_out()
    tree.add((fork(5, taken=False), fork(7, taken=True), fork(9, taken=True), fork(8, taken=True)))

    aims = [(picked.path, picked.aim.position) for picked in iter(tree.next, None)]

    # the later path's new sides deepest first, but for the one at line 9, which is last
    assert aims == [(1, 3), (1, 1), (1, 2)]


def test_a_fork_waiting_for_the_last_picks_keeps_its_path_to_extend() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(9, taken=True)))
    tree.add((fork(3, taken=True), fork(9, taken=True)))
    tree.next()
    tree.timed_out()
    tree.next()
    tree.next()

    # the second path's fork at line 9 is open, and waits for the last picks
    assert tree.oldest == 1
    picked = tree.next()

    assert picked is not None and (picked.path, picked.aim.position) == (1, 1)
    assert tree.oldest == 2
    assert tree.next() is None


def test_a_fork_is_aimed_at_once() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))

    first = tree.next()
    second = tree.next()

    assert first is not None and second is not None
    # the deepest fork was aimed at, so the next pick moves up the path
    assert first.aim == Aim(site=fork(3, taken=True).site, position=1)
    assert second.aim == Aim(site=fork(2, taken=True).site, position=0)
    assert tree.next() is None


def test_a_fork_both_sides_of_which_ran_is_never_aimed_at() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True),))
    tree.add((fork(2, taken=False),))

    assert tree.next() is None


def test_a_nested_fork_both_sides_of_which_ran_is_never_aimed_at() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(5, taken=True)))
    tree.add((fork(2, taken=True), fork(5, taken=False)))

    picked = tree.next()

    # line 5 ran both ways under this prefix, so the pick moves up to line 2
    assert picked is not None
    assert picked.aim == Aim(site=fork(2, taken=True).site, position=0)
    assert tree.next() is None


def test_the_same_site_under_a_different_prefix_is_a_different_fork() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(5, taken=True)))
    tree.add((fork(2, taken=False), fork(5, taken=False)))

    picks = [picked.prefix for picked in iter(tree.next, None)]

    # line 5 ran one way under each prefix, so each is still open, the oldest path's first
    assert picks == [
        (fork(2, taken=True), fork(5, taken=False)),
        (fork(2, taken=False), fork(5, taken=True)),
    ]


def test_the_forks_of_a_later_path_join_the_pool() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True),))
    tree.next()
    tree.add((fork(2, taken=False), fork(4, taken=True)))

    picked = tree.next()

    assert picked is not None
    assert picked.prefix == (fork(2, taken=False), fork(4, taken=False))
    assert picked.aim == Aim(site=fork(4, taken=True).site, position=1)


def test_a_long_path_is_added_in_linear_time() -> None:
    """Why a timing test: recording a path must cost the path's length, not its square.

    A loop leaves one fork per pass, so a looping target's seed hands the
    tree thousands of forks at one site. A key that copies the prefix turns
    that into minutes, and the run outlives its budget before it can say so.
    """
    path = tuple(fork(2, taken=True) for _ in range(3_000))

    started = time.perf_counter()
    Tree().add(path)

    assert time.perf_counter() - started < 1.0


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count every fork a pick reads; the count is the list's one item."""
    reads = [0]
    read = Tree._open

    def counted(tree: Tree, key: ForkKey, taken: bool) -> bool:
        reads[0] += 1
        return read(tree, key, taken)

    monkeypatch.setattr(Tree, "_open", counted)
    return reads


def test_the_picks_over_a_loop_s_many_paths_read_each_fork_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pick must not reread forks that earlier picks already ruled out.

    A loop hands the tree one path per input, each thousands of forks long
    and nearly all of them shared with an older path. Once the older paths
    are spent, reading them again on every pick costs their square each
    time. The picks here take the other side of the loop's fork, as a
    countdown's inputs would: one more pass, or the loop ending there. So
    the picks read at most every fork the tree holds, once.
    """
    reads = _counting(monkeypatch)
    tree = Tree()
    held = 1_001
    tree.add((*(fork(2, taken=True) for _ in range(held - 1)), fork(2, taken=False)))
    for _ in range(1_100):
        picked = tree.next()
        assert picked is not None
        ending = (fork(2, taken=False),) if picked.prefix[-1].taken else ()
        path = (*picked.prefix, *ending)
        tree.add(path)
        held += len(path)

    assert reads[0] <= held


def test_the_picks_over_many_new_sides_read_each_fork_at_most_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each path's new sides stop being new when the next path takes the other ones.

    A fork read once as a new side and found taken since is not read as a
    new side again, so a pick costs no rescan of the paths before it: at most
    one read of each fork as a new side, and one in the oldest-path order.
    """
    reads = _counting(monkeypatch)
    tree = Tree()
    held = 0
    for index in range(300):
        path = tuple(fork(line, taken=index % 2 == 0) for line in range(2, 202))
        tree.add(path)
        held += len(path)
        tree.next()

    assert reads[0] <= 2 * held


def test_a_fresh_path_leaves_each_of_its_forks_untried() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))

    assert tree.untried() == {fork(2, taken=True).where: 1, fork(3, taken=True).where: 1}


def test_an_aimed_fork_and_a_fork_whose_other_side_ran_are_not_untried() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))
    tree.next()
    # the other side of line 2 ran, so line 2's fork is closed without an aim
    tree.add((fork(2, taken=False),))

    assert tree.untried() == {}


def test_a_fork_two_paths_share_is_counted_once_and_one_site_under_two_prefixes_twice() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True), fork(3, taken=True)))
    tree.add((fork(2, taken=True), fork(3, taken=True), fork(4, taken=True)))
    tree.add((fork(2, taken=False), fork(3, taken=True)))

    # line 2 had both sides run; line 3 sits under two prefixes, each its own fork
    assert tree.untried() == {fork(3, taken=True).where: 2, fork(4, taken=True).where: 1}


def test_a_test_and_an_operation_s_fork_at_one_column_are_counted_apart() -> None:
    tree = Tree()
    test = fork(2, taken=True)
    operation = Branch(expression=[">", "x", 0], taken=True, site=test.site, raising=True)
    tree.add((operation, test))

    assert tree.untried() == {test.where: 1, operation.where: 1}


def test_an_operation_s_side_at_a_test_s_column_does_not_make_the_test_s_flip_old() -> None:
    tree = Tree()
    test = fork(2, taken=False)
    # `if s[0] == "q":`: the index's long-enough fork, taken true, at the test's own column
    index = Branch(expression=[">", "x", 0], taken=True, site=test.site, raising=True)
    tree.add((index, test, fork(3, taken=True)))
    # line 3's other side ran on another path: its fork here is still open, but not new
    tree.add((fork(3, taken=False),))

    picked = tree.next()

    # the test's true side is new, whatever the index's fork took at that column, so it comes
    # before line 3, which the oldest-path order would pick
    assert picked is not None
    assert (picked.aim.site, picked.aim.raising) == (test.site, False)


def test_the_oldest_path_a_pick_can_still_extend_moves_on_as_paths_are_spent() -> None:
    tree = Tree()
    tree.add((fork(2, taken=True),))
    tree.add((fork(2, taken=False), fork(3, taken=True)))

    # both sides of line 2 ran, so the first path has no fork left and no later pick extends it
    assert tree.oldest == 1
    picked = tree.next()

    assert picked is not None and picked.path == 1 and picked.aim.position == 1
    # the pick spent the last open fork, so no path is left to extend
    assert tree.oldest == 2
    assert tree.next() is None


def test_a_pick_plans_with_the_facts_its_own_path_held_before_the_fork() -> None:
    tree = Tree()
    site = Site(file="m.py", line=9, col=4)
    held = Fact([">", "n", 0], True, site, after=0)
    placed = Fact(None, True, site, place=["walked", "d", "'a'"], after=1)
    tree.add((fork(2, taken=True),), (held, placed))
    # another input that took the same fork, whose walk read another key there
    tree.add((fork(2, taken=True),), (Fact(None, True, site, place=["walked", "d", "'b'"]),))

    picked = tree.next()

    assert picked is not None and picked.path == 0
    assert picked.facts == (held,)


def test_facts_add_no_fork_to_aim_at() -> None:
    tree = Tree()
    tree.add((), (Fact([">", "n", 0], True, Site(file="m.py", line=9, col=4)),))

    assert tree.next() is None
    assert tree.untried() == {}
