from pyct.branches.compare import compare

from pyct.core.branch import Branch, Site


def fork(line: int, *, taken: bool) -> Branch:
    """A fork on x at its own line, so the forks of a path are told apart."""
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def test_a_path_that_is_the_plan_followed_it() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))

    assert compare(planned, planned) is None


def test_a_path_may_go_on_past_the_plan() -> None:
    planned = (fork(2, taken=True),)
    actual = (fork(2, taken=True), fork(3, taken=False))

    assert compare(planned, actual) is None


def test_a_fork_the_plan_wanted_that_never_happened_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(2, taken=True),)

    assert compare(planned, actual) == 1


def test_a_fork_taken_the_other_way_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(2, taken=True), fork(3, taken=True))

    assert compare(planned, actual) == 1


def test_a_fork_at_another_site_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(9, taken=True), fork(3, taken=False))

    assert compare(planned, actual) == 0
