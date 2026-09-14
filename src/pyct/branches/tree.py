"""Every path a run has taken, and the fork it aims at next."""

from pyct.branches.plan import Plan, plan
from pyct.core.branch import Branch, Site

# what tells one fork from another: the id of the fork before it, -1 at the root, then its own site
type ForkKey = tuple[int, Site]


class Tree:
    """The paths of a run and which of their forks are still open.

    A fork is its prefix plus its site, so the same ``if`` reached through a
    different sequence of sides is a different fork. It is open until an
    input aims at it or its other side runs, and it is aimed at once,
    whatever the solver answers; ``README.md › Rules › forks``.

    A path's prefix is interned: every site and side under a parent gets one
    id, and paths that share a prefix walk the same ids along it, so a fork
    names its prefix with that id instead of a copy of it. Copying would
    cost the square of the path's length, and a loop hands the tree a path
    with one fork per pass. A side enters the id table when an input runs
    it, so the table also says which sides ran.
    """

    def __init__(self) -> None:
        self._ids: dict[tuple[int, Site, bool], int] = {}
        self._paths: list[tuple[tuple[Branch, ...], tuple[ForkKey, ...]]] = []
        self._aimed: set[ForkKey] = set()

    def add(self, forks: tuple[Branch, ...]) -> None:
        """Record the path one input took. Its forks join the pool the next pick draws from."""
        parent: int = -1
        keys: list[ForkKey] = []
        for fork in forks:
            key = (parent, fork.site)
            parent = self._ids.setdefault((parent, fork.site, fork.taken), len(self._ids))
            keys.append(key)
        self._paths.append((forks, tuple(keys)))

    def next(self) -> Plan | None:
        """The path that takes the other side of the deepest open fork on the newest path.

        Newest path first, deepest fork first, by decision
        fork-order-newest-path-deepest-first: that fork shares the longest
        concrete prefix with the path that just ran. The pick is the aim, so
        the fork is spent whether or not the solver answers.
        """
        for forks, keys in reversed(self._paths):
            for at in reversed(range(len(forks))):
                if self._open(keys[at], forks[at].taken):
                    self._aimed.add(keys[at])
                    return plan(forks[: at + 1])
        return None

    def _open(self, key: ForkKey, taken: bool) -> bool:
        """A fork no input aimed at, whose other side no input ran."""
        parent, site = key
        return key not in self._aimed and (parent, site, not taken) not in self._ids
