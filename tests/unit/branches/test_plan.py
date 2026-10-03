from pyct.branches.plan import plan
from pyct.core.branch import Branch, Fact, Site
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


def placed(after: int) -> Fact:
    """A place a walk read, recorded after ``after`` forks."""
    return Fact(None, True, Site("m.py", 9, 4), place=["walked", "d", f"'{after}'"], after=after)


def test_a_fact_recorded_before_the_flipped_fork_is_kept_and_one_after_it_dropped() -> None:
    forks = (fork(2, taken=True), fork(3, taken=True))
    facts = (placed(0), placed(1), placed(2))

    planned = plan(forks, 0, facts)

    assert planned is not None
    # the place recorded after the second fork held only on the side the path took
    assert planned.facts == (placed(0), placed(1))


def test_a_plan_asks_its_forks_and_kept_facts_in_the_order_they_were_recorded() -> None:
    forks = (fork(2, taken=True), fork(3, taken=True), fork(4, taken=False))
    decided = Fact([">", "n", 0], True, Site("m.py", 5, 4), after=2)
    facts = (placed(0), placed(1), placed(1), decided, placed(3))

    planned = plan(forks, 0, facts)

    assert planned is not None
    assert planned.asked == (
        placed(0),
        forks[0],
        placed(1),
        placed(1),
        forks[1],
        decided,
        fork(4, taken=True),
    )


def test_a_plan_with_no_facts_asks_its_forks() -> None:
    forks = (fork(2, taken=True), fork(3, taken=False))

    planned = plan(forks)

    assert planned is not None and planned.asked == planned.prefix
