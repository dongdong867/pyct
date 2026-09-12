from pyct.branches.plan import plan
from pyct.core.branch import Branch, Site
from pyct.results.record import Aim


def fork(line: int, *, taken: bool) -> Branch:
    """A fork on x at its own line, so the forks of a path are told apart."""
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def test_a_path_with_no_fork_has_nothing_to_flip() -> None:
    assert plan(()) is None


def test_one_fork_is_planned_the_other_way() -> None:
    only = fork(2, taken=True)

    planned = plan((only,))

    assert planned is not None
    assert planned.prefix == (fork(2, taken=False),)
    assert planned.aim == Aim(site=only.site, position=0)


def test_only_the_last_fork_of_a_path_is_flipped() -> None:
    forks = (fork(2, taken=True), fork(3, taken=False), fork(4, taken=True))

    planned = plan(forks)

    assert planned is not None
    assert planned.prefix == (forks[0], forks[1], fork(4, taken=False))
    assert planned.aim == Aim(site=forks[2].site, position=2)


def test_the_path_it_was_given_is_left_alone() -> None:
    forks = (fork(2, taken=True),)

    planned = plan(forks)

    assert planned is not None
    assert planned.prefix is not forks
    assert forks == (fork(2, taken=True),)
