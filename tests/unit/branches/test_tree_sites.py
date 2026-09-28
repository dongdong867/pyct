"""The tree tells sites apart by value, whatever object holds each one."""

from pyct.branches.tree import Tree
from pyct.core.branch import Branch, ForkSite, Site


def test_two_objects_for_one_site_are_one_site() -> None:
    tree = Tree()
    tree.add((Branch(expression=["<", "x", 2], taken=True, site=Site("m.py", 2, 7)),))
    tree.add((Branch(expression=["<", "x", 2], taken=False, site=Site("m.py", 2, 7)),))

    # both sides of the one fork ran, so nothing is left to aim at or to try
    assert tree.next() is None
    assert tree.untried() == {}


def test_untried_forks_are_counted_by_the_site_they_share() -> None:
    tree = Tree()
    first = Site("m.py", 3, 7)
    tree.add(
        (
            Branch(expression=["<", "x", 2], taken=True, site=first),
            Branch(expression=["<", "x", 3], taken=True, site=Site("m.py", 3, 7)),
            Branch(expression=["<", "x", 4], taken=True, site=Site("m.py", 4, 7), raising=True),
        )
    )

    assert tree.untried() == {
        ForkSite(Site("m.py", 3, 7)): 2,
        ForkSite(Site("m.py", 4, 7), raising=True): 1,
    }
