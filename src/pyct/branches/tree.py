"""Every path a run has taken, and the fork it aims at next."""

from collections import deque

from pyct.branches.plan import Plan, plan
from pyct.core.branch import Branch, Site

# what tells one fork from another: the id of the fork before it, -1 at the root, then its own site
type ForkKey = tuple[int, Site]

# one input's path: the forks it took, and the key of each
type Walked = tuple[tuple[Branch, ...], tuple[ForkKey, ...]]

# a fork where it sits in the tree: its path's index, and its position on that path
type Place = tuple[int, int]


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

    Apart from the prefix, the tree keeps every side any input took at each
    site, whatever came before it: a fork whose other side is in no input
    yet is a new side, and the pick tries those first (see `next`).

    A pick whose ask ran to the solver's limit turns the rest of its path's
    new sides shallowest first, and every other fork at its site waits until
    each fork elsewhere was aimed at (see `timed_out`).
    """

    def __init__(self) -> None:
        self._ids: dict[tuple[int, Site, bool], int] = {}
        self._paths: list[Walked] = []
        self._aimed: set[ForkKey] = set()
        self._sides: set[tuple[Site, bool]] = set()
        # the forks that were new sides when their path arrived, oldest path first and deepest
        # fork first, or shallowest first on a path a timeout turned (`timed_out`). A path's
        # forks sit together, so after a pick the rest of its path leads the queue. A side taken
        # never becomes new again, so a fork leaves for good
        self._new: deque[Place] = deque()
        # where the oldest-path pick starts looking: the oldest path that may still hold an open
        # fork, and the deepest position on it that may, None before the pick first reaches the
        # path. A fork that closes never opens again, so every fork past this point is spent
        self._path = 0
        self._depth: int | None = None
        # the path and the site of the last pick, the paths whose new sides a timeout turned,
        # and the sites a pick timed out at
        self._picked: int | None = None
        self._picked_site: Site | None = None
        self._turned: set[int] = set()
        self._timed_out: set[Site] = set()
        # the open forks at a site a pick timed out at, in the order the oldest-path pick passed
        # them, oldest path first and deepest fork first: the last picks (`_next_later`)
        self._later: deque[Place] = deque()

    def add(self, forks: tuple[Branch, ...]) -> None:
        """Record the path one input took. Its forks join the pool the next pick draws from."""
        parent: int = -1
        keys: list[ForkKey] = []
        for fork in forks:
            key = (parent, fork.site)
            parent = self._ids.setdefault((parent, fork.site, fork.taken), len(self._ids))
            keys.append(key)
            self._sides.add((fork.site, fork.taken))
        index = len(self._paths)
        self._paths.append((forks, tuple(keys)))
        self._new.extend(
            (index, depth) for depth in reversed(range(len(forks))) if self._new_side(forks[depth])
        )

    @property
    def oldest(self) -> int:
        """The oldest path a pick may still extend: every path before it has no open fork, and
        a fork never reopens, so no later pick names one of those."""
        self._seek()
        return min(self._path, self._later[0][0]) if self._later else self._path

    def next(self) -> Plan | None:
        """The path that takes the other side of the open fork the order picks next, and which
        path it extends, counted in the order ``add`` took them.

        New side first, by decision fork-order-shallowest-first-after-a-timeout:
        an open fork whose other side no input took at its site comes first,
        oldest path first and deepest fork first, or shallowest first on a
        path a pick timed out on (`timed_out`); otherwise the deepest open
        fork on the oldest path; and last, a fork at a site a pick timed out
        at, oldest path first and deepest fork first. A loop's test takes both
        sides on a path that runs it, so a loop that adds a pass on every
        input cannot starve the forks around it, and the seed's last fork is
        the first pick unless its other side already ran (flip-one-fork). The
        pick is the aim, so the fork is spent whether or not the solver answers. Each order resumes where it last
        stopped, so a run's picks read each fork at most once in each.
        """
        picked = self._next_new_side() or self._next_oldest() or self._next_later()
        if picked is None:
            return None
        path, depth = picked
        forks, keys = self._paths[path]
        self._aimed.add(keys[depth])
        self._picked, self._picked_site = path, forks[depth].site
        return plan(forks[: depth + 1], path)

    def timed_out(self) -> None:
        """The last pick's ask ran to the solver's limit: its path's other new sides, still
        waiting, go shallowest first, once per path, and every fork at its site on any path
        waits until each fork elsewhere was aimed at.

        The ask for a fork holds the path up to it, so after one ran out of
        time, the next deepest holds nearly the same and would likely run out
        too, spending the budget on one input; the shallowest holds the
        least. A fork at the same site asks the same condition of the same
        kind of value, as `int(s)` after `s.isdigit()` does in each call of a
        helper, which only a string of more digits than Python reads flips,
        so it would likely run out as well. Decisions
        fork-order-shallowest-first-after-a-timeout and
        fork-order-a-timed-out-site-waits-for-the-last-picks.
        """
        if self._picked_site is not None:
            self._timed_out.add(self._picked_site)
        path = self._picked
        if path is None or path in self._turned:
            return
        self._turned.add(path)
        waiting: list[Place] = []
        while self._new and self._new[0][0] == path:
            waiting.append(self._new.popleft())
        # extendleft puts them back in reverse: shallowest first
        self._new.extendleft(waiting)

    def _next_new_side(self) -> Place | None:
        """The first fork waiting as a new side that is still open and still new.

        A fork an input has since taken the other side of, anywhere, leaves the queue here and
        waits for the oldest-path order instead, and so does one at a site a pick timed out at,
        which that order passes on to the last picks.
        """
        while self._new:
            path, depth = self._new.popleft()
            forks, keys = self._paths[path]
            fork = forks[depth]
            waits = fork.site in self._timed_out
            if not waits and self._open(keys[depth], fork.taken) and self._new_side(fork):
                return path, depth
        return None

    def _next_oldest(self) -> Place | None:
        """The deepest open fork on the oldest path that holds one."""
        found = self._seek()
        if found is not None:
            self._depth = found[1] - 1
        return found

    def _next_later(self) -> Place | None:
        """The first fork at a site a pick timed out at that is still open."""
        while self._later:
            path, depth = self._later.popleft()
            forks, keys = self._paths[path]
            if self._open(keys[depth], forks[depth].taken):
                return path, depth
        return None

    def _seek(self) -> Place | None:
        """Move where the oldest-path pick starts looking to the deepest open fork on the oldest
        path that holds one, and name it; None when no path holds one. An open fork at a site a
        pick timed out at is passed on to the last picks."""
        while self._path < len(self._paths):
            depth = self._deepest_pickable()
            if depth >= 0:
                self._depth = depth
                return self._path, depth
            self._path += 1
            self._depth = None
        return None

    def _deepest_pickable(self) -> int:
        """The deepest position from where the oldest-path pick starts looking that holds an open
        fork at a site no pick timed out at, or -1; each open fork passed on the way waits for
        the last picks."""
        forks, keys = self._paths[self._path]
        depth = len(forks) - 1 if self._depth is None else self._depth
        while depth >= 0:
            fork = forks[depth]
            if self._open(keys[depth], fork.taken):
                if fork.site not in self._timed_out:
                    return depth
                self._later.append((self._path, depth))
            depth -= 1
        return depth

    def _new_side(self, fork: Branch) -> bool:
        """Whether no input took the other side of this fork's site, whatever came before it."""
        return (fork.site, not fork.taken) not in self._sides

    def _open(self, key: ForkKey, taken: bool) -> bool:
        """A fork no input aimed at, whose other side no input ran."""
        parent, site = key
        return key not in self._aimed and (parent, site, not taken) not in self._ids
