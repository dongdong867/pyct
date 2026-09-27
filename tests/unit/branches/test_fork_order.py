"""The tree's pick order against the order written plainly: every pick reads every fork again.

The tree keeps cursors so a pick never rereads a fork it has ruled out, and
decides a fork's tier once, when its path arrives. The reference here keeps
nothing between picks, so the two agree only if the cursors skip nothing
and the tiers are right (fork-order-shallowest-first-after-a-timeout).
"""

import random

import pytest

from pyct.branches.plan import Plan, plan
from pyct.branches.tree import Tree
from pyct.core.branch import Branch, Site

# a side of a fork: where it happened, and which way it went
type Side = tuple[Site, bool]


class Rescan:
    """The fork order, read afresh on every pick.

    A fork is open while no pick aimed at it and no input took its other
    side after the same prefix. A fork whose other side no input took
    anywhere comes first, oldest path first and deepest fork first, or
    shallowest first on a path a pick timed out on; then every other open
    fork, oldest path first and deepest fork first; each of those at a site
    no pick timed out at. Last come the open forks at such a site, oldest
    path first and deepest fork first.
    """

    def __init__(self) -> None:
        self.paths: list[tuple[Branch, ...]] = []
        self.walked: set[tuple[Side, ...]] = set()
        self.aimed: set[tuple[tuple[Side, ...], Site]] = set()
        self.sides: set[Side] = set()
        self.picked: int | None = None
        self.picked_site: Site | None = None
        self.turned: set[int] = set()
        self.timed_out_at: set[Site] = set()

    def add(self, forks: tuple[Branch, ...]) -> None:
        self.paths.append(forks)
        walked: tuple[Side, ...] = ()
        for fork in forks:
            walked = (*walked, (fork.site, fork.taken))
            self.walked.add(walked)
            self.sides.add((fork.site, fork.taken))

    def next(self) -> Plan | None:
        for tier in ("new side", "open", "last"):
            for path, forks in enumerate(self.paths):
                turned = tier == "new side" and path in self.turned
                for at in range(len(forks)) if turned else reversed(range(len(forks))):
                    if self._open(forks, at) and self._in(tier, forks[at]):
                        self.aimed.add(self._key(forks, at))
                        self.picked, self.picked_site = path, forks[at].site
                        return plan(forks[: at + 1], path)
        return None

    def timed_out(self) -> None:
        if self.picked_site is not None:
            self.timed_out_at.add(self.picked_site)
        if self.picked is not None:
            self.turned.add(self.picked)

    def _in(self, tier: str, fork: Branch) -> bool:
        if tier == "last":
            return True
        return fork.site not in self.timed_out_at and (tier == "open" or self._new_side(fork))

    def _key(self, forks: tuple[Branch, ...], at: int) -> tuple[tuple[Side, ...], Site]:
        return tuple((fork.site, fork.taken) for fork in forks[:at]), forks[at].site

    def _open(self, forks: tuple[Branch, ...], at: int) -> bool:
        before, site = self._key(forks, at)
        other = (*before, (site, not forks[at].taken))
        return (before, site) not in self.aimed and other not in self.walked

    def _new_side(self, fork: Branch) -> bool:
        return (fork.site, not fork.taken) not in self.sides


def _fork(line: int, taken: bool) -> Branch:
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def _random_forks(rng: random.Random, most: int) -> tuple[Branch, ...]:
    """A few forks over four sites, so sides repeat within a path and across paths."""
    return tuple(_fork(rng.randint(1, 4), rng.random() < 0.5) for _ in range(rng.randint(0, most)))


def _after(rng: random.Random, picked: Plan) -> tuple[Branch, ...]:
    """The path an input took for a plan: it followed the plan and ran on, or left it early."""
    kept = len(picked.prefix) if rng.random() < 0.7 else rng.randint(0, len(picked.prefix))
    return (*picked.prefix[:kept], *_random_forks(rng, 4))


@pytest.mark.parametrize("seed", range(300))
def test_the_tree_picks_what_a_full_rescan_picks(seed: int) -> None:
    rng = random.Random(seed)
    tree, reference = Tree(), Rescan()
    for _ in range(60):
        # a path from nowhere, an input that ran on a plan, or a plan the solver answered
        # nothing for, which adds no path
        if rng.random() < 0.3:
            path = _random_forks(rng, 6)
            tree.add(path)
            reference.add(path)
            continue
        picked = tree.next()
        assert picked == reference.next()
        if picked is not None and rng.random() < 0.8:
            path = _after(rng, picked)
            tree.add(path)
            reference.add(path)
        elif rng.random() < 0.5:
            # the solver ran out of time on the plan
            tree.timed_out()
            reference.timed_out()
