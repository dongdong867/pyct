import time

from pyct.branches.tree import Tree
from pyct.core.branch import Branch, Site
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


def test_a_path_added_after_a_pick_waits_behind_the_older_open_forks() -> None:
    """The loop's case: each input adds a pass, and the forks before the loop still come first."""
    tree = Tree()
    tree.add((fork(2, taken=False), fork(3, taken=True), fork(3, taken=False)))
    first = tree.next()
    tree.add((fork(2, taken=False), fork(3, taken=True), fork(3, taken=True), fork(3, taken=False)))

    later = [picked.aim.position for picked in iter(tree.next, None)]

    assert first is not None and first.aim.position == 2
    # the seed's path first, deepest to shallowest, then the newer path's own fork
    assert later == [1, 0, 3]


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


def test_the_picks_over_a_loop_s_many_paths_take_linear_time() -> None:
    """Why a timing test: a pick must not rescan forks that earlier picks already ruled out.

    A loop hands the tree one path per input, each thousands of forks long
    and nearly all of them shared with an older path. Once the older paths
    are spent, scanning them again on every pick costs their square each
    time. The picks here take the other side of the loop's fork, as a
    countdown's inputs would: one more pass, or the loop ending there.
    """
    tree = Tree()
    tree.add((*(fork(2, taken=True) for _ in range(1_000)), fork(2, taken=False)))
    started = time.perf_counter()
    for _ in range(1_100):
        picked = tree.next()
        assert picked is not None
        ending = (fork(2, taken=False),) if picked.prefix[-1].taken else ()
        tree.add((*picked.prefix, *ending))

    assert time.perf_counter() - started < 3.0
