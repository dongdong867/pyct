"""Every path a run has taken, and the fork it aims at next."""

from pyct.branches.plan import Plan, plan
from pyct.core.branch import Branch, Site

# what tells one fork from another: the side every fork before it took, then its own site
type ForkKey = tuple[tuple[tuple[Site, bool], ...], Site]


class Tree:
    """The paths of a run and which of their forks are still open.

    A fork is its prefix plus its site, so the same ``if`` reached through a
    different sequence of sides is a different fork. It is open until an
    input aims at it or its other side runs, and it is aimed at once,
    whatever the solver answers; ``README.md › Rules › forks``.
    """

    def __init__(self) -> None:
        self._paths: list[tuple[Branch, ...]] = []
        self._seen: set[tuple[ForkKey, bool]] = set()
        self._aimed: set[ForkKey] = set()

    def add(self, forks: tuple[Branch, ...]) -> None:
        """Record the path one input took. Its forks join the pool the next pick draws from."""
        self._paths.append(forks)
        for at, fork in enumerate(forks):
            self._seen.add((_key(forks, at), fork.taken))

    def next(self) -> Plan | None:
        """The path that takes the other side of the deepest open fork on the newest path.

        Newest path first, deepest fork first, by decision
        fork-order-newest-path-deepest-first: that fork shares the longest
        concrete prefix with the path that just ran. The pick is the aim, so
        the fork is spent whether or not the solver answers.
        """
        for forks in reversed(self._paths):
            for at in reversed(range(len(forks))):
                key = _key(forks, at)
                if self._open(key, forks[at].taken):
                    self._aimed.add(key)
                    return plan(forks[: at + 1])
        return None

    def _open(self, key: ForkKey, taken: bool) -> bool:
        """A fork no input aimed at, whose other side no input ran."""
        return key not in self._aimed and (key, not taken) not in self._seen


def _key(forks: tuple[Branch, ...], at: int) -> ForkKey:
    """The identity of the fork at ``at`` on ``forks``.

    A ``Branch`` holds its condition as a list and cannot be hashed, so the
    key carries the site and the side of each fork before it, which is what
    says where this one sits.
    """
    return (tuple((fork.site, fork.taken) for fork in forks[:at]), forks[at].site)
