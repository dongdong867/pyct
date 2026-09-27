"""Every path a run has taken, and the fork it aims at next."""

from pyct.branches.plan import Plan, plan
from pyct.core.branch import Branch, Site

# what tells one fork from another: the id of the fork before it, -1 at the root, then its own site
type ForkKey = tuple[int, Site]

# one input's path: the forks it took, and the key of each
type Walked = tuple[tuple[Branch, ...], tuple[ForkKey, ...]]


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
        self._paths: list[Walked] = []
        self._aimed: set[ForkKey] = set()
        # where the next pick starts looking: the oldest path that may still hold an open fork,
        # and the deepest position on it that may, None before the pick first reaches the path.
        # A fork that closes never opens again, so every fork past this point is spent
        self._path = 0
        self._depth: int | None = None

    def add(self, forks: tuple[Branch, ...]) -> None:
        """Record the path one input took. Its forks join the pool the next pick draws from."""
        parent: int = -1
        keys: list[ForkKey] = []
        for fork in forks:
            key = (parent, fork.site)
            parent = self._ids.setdefault((parent, fork.site, fork.taken), len(self._ids))
            keys.append(key)
        self._paths.append((forks, tuple(keys)))

    @property
    def oldest(self) -> int:
        """The oldest path a pick may still extend: every path before it has no open fork, and
        a fork never reopens, so no later pick names one of those."""
        return self._path

    def next(self) -> Plan | None:
        """The path that takes the other side of the deepest open fork on the oldest path, and
        which path it extends, counted in the order ``add`` took them.

        Oldest path first, deepest fork first, by decision
        fork-order-oldest-path-deepest-first: every fork of a path is tried
        before a newer path's, so a loop that adds a pass on every input
        cannot starve the forks before it, and the seed's last fork is the
        first pick (flip-one-fork). The pick is the aim, so the fork is spent
        whether or not the solver answers. The search resumes where the last
        one stopped, so a run's picks cost its forks once, not once a pick.
        """
        while self._path < len(self._paths):
            forks, keys = self._paths[self._path]
            depth = len(forks) - 1 if self._depth is None else self._depth
            while depth >= 0 and not self._open(keys[depth], forks[depth].taken):
                depth -= 1
            if depth >= 0:
                self._aimed.add(keys[depth])
                self._depth = depth - 1
                return plan(forks[: depth + 1], self._path)
            self._path += 1
            self._depth = None
        return None

    def _open(self, key: ForkKey, taken: bool) -> bool:
        """A fork no input aimed at, whose other side no input ran."""
        parent, site = key
        return key not in self._aimed and (parent, site, not taken) not in self._ids
