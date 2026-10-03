"""Every path a run has taken, and the fork it aims at next."""

from collections import Counter, deque

from pyct.branches.plan import Plan, plan
from pyct.core.branch import Branch, Fact, ForkSite, Site

# what tells one fork from another: the id of the fork before it, -1 at the root, then its own
# site's number (see `Tree._number`)
type ForkKey = tuple[int, int]

# one input's path: the forks it took, the key of each, and the facts it held beside them
type Walked = tuple[tuple[Branch, ...], tuple[ForkKey, ...], tuple[Fact, ...]]

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

    A walk's ``len(<form>) > k`` fork over a split's list (``Branch.split_walk``)
    is aimed at last of all, oldest path first and deepest fork first, once no
    other fork is left: each flip of one changes how many pieces the string
    has, which costs seconds on a long loop, and v2, which has no such fork,
    spends that time on the loop's content forks (decision
    fork-order-a-split-s-walk-forks-after-the-path-s-other-forks).

    Each site gets a number the first time the tree meets it, and the tree
    keys a fork by that number: a ``Site`` hashes in Python, a number in C,
    and a path of 100,000 forks hashes its sites half a million times.
    """

    def __init__(self) -> None:
        # each site met, by value, as its number; each number's site; and each number by the
        # identity of every Site object met, which a path's forks keep alive, so no id is reused
        self._number_by_value: dict[Site, int] = {}
        self._sites: list[Site] = []
        self._number_by_identity: dict[int, int] = {}
        self._ids: dict[tuple[int, int, bool], int] = {}
        self._paths: list[Walked] = []
        self._aimed: set[ForkKey] = set()
        # each side taken, as a plain tuple: its site's number, a fork before a raise, the side
        self._sides: set[tuple[int, bool, bool]] = set()
        # the forks that were new sides when their path arrived, oldest path first and deepest
        # fork first, or shallowest first on a path a timeout turned (`timed_out`); a path's
        # forks sit together, and a side taken never becomes new again
        self._new: deque[Place] = deque()
        # where the oldest-path pick, and the split walks' pick, start looking: the oldest path
        # that may still hold an open fork, and the deepest position on it that may, None
        # before the pick first reaches the path; a fork that closes never opens again
        self._path = 0
        self._depth: int | None = None
        self._walk_path = 0
        self._walk_depth: int | None = None
        # the path and the site number of the last pick, the paths whose new sides a timeout
        # turned, and the sites' numbers a pick timed out at
        self._picked: int | None = None
        self._picked_number: int | None = None
        self._turned: set[int] = set()
        self._timed_out: set[int] = set()
        # the open forks at a site a pick timed out at, in the order the oldest-path pick passed
        # them, oldest path first and deepest fork first: the last picks (`_next_later`)
        self._later: deque[Place] = deque()

    def add(self, forks: tuple[Branch, ...], facts: tuple[Fact, ...] = ()) -> None:
        """Record the path one input took. Its forks join the pool the next pick draws from.

        Its facts stay beside its forks, the path's own: two inputs that share a fork can read
        different keys at one place. Only the plan reads them; no key, queue or count does.
        """
        parent: int = -1
        keys: list[ForkKey] = []
        for fork in forks:
            number = self._number_by_identity.get(id(fork.site))
            if number is None:
                number = self._number(fork.site)
            keys.append((parent, number))
            parent = self._ids.setdefault((parent, number, fork.taken), len(self._ids))
            self._sides.add((number, fork.raising, fork.taken))
        index = len(self._paths)
        self._paths.append((forks, tuple(keys), facts))
        self._new.extend(
            (index, depth)
            for depth in reversed(range(len(forks)))
            if not forks[depth].split_walk and self._new_side(keys[depth], forks[depth])
        )

    def _number(self, site: Site) -> int:
        """The site's number, given the first time the tree meets a site equal to it."""
        number = self._number_by_value.setdefault(site, len(self._number_by_value))
        if number == len(self._sites):
            self._sites.append(site)
        self._number_by_identity[id(site)] = number
        return number

    @property
    def oldest(self) -> int:
        """The oldest path a pick may still extend: every path before it has no open fork, and
        a fork never reopens, so no later pick names one of those."""
        self._seek()
        self._seek_walk()
        oldest = min(self._path, self._walk_path)
        return min(oldest, self._later[0][0]) if self._later else oldest

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
        pick is the aim, so the fork is spent whether or not the solver
        answers. Each order resumes where it last stopped, so a run's picks
        read each fork at most once in each.
        """
        picked = self._next_new_side() or self._next_oldest() or self._next_later()
        picked = picked or self._next_walk()
        if picked is None:
            return None
        path, depth = picked
        forks, keys, facts = self._paths[path]
        self._aimed.add(keys[depth])
        self._picked, self._picked_number = path, keys[depth][1]
        return plan(forks[: depth + 1], path, facts)

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
        if self._picked_number is not None:
            self._timed_out.add(self._picked_number)
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
            forks, keys, _ = self._paths[path]
            fork, key = forks[depth], keys[depth]
            waits = key[1] in self._timed_out
            if not waits and self._open(key, fork.taken) and self._new_side(key, fork):
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
            forks, keys, _ = self._paths[path]
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
        forks, keys, _ = self._paths[self._path]
        depth = len(forks) - 1 if self._depth is None else self._depth
        while depth >= 0:
            key = keys[depth]
            if not forks[depth].split_walk and self._open(key, forks[depth].taken):
                if key[1] not in self._timed_out:
                    return depth
                self._later.append((self._path, depth))
            depth -= 1
        return depth

    def _next_walk(self) -> Place | None:
        """The deepest open split walk on the oldest path that holds one."""
        if not self._seek_walk():
            return None
        depth = self._walk_depth
        assert depth is not None
        self._walk_depth = depth - 1
        return self._walk_path, depth

    def _seek_walk(self) -> bool:
        """Move where the split walks' pick starts looking to the deepest open one on the oldest
        path that holds one; False when no path does."""
        while self._walk_path < len(self._paths):
            forks, keys, _ = self._paths[self._walk_path]
            depth = len(forks) - 1 if self._walk_depth is None else self._walk_depth
            while depth >= 0:
                if forks[depth].split_walk and self._open(keys[depth], forks[depth].taken):
                    self._walk_depth = depth
                    return True
                depth -= 1
            self._walk_path, self._walk_depth = self._walk_path + 1, None
        return False

    def _new_side(self, key: ForkKey, fork: Branch) -> bool:
        """Whether no input took the other side of this fork's site, whatever came before it.

        A site is told apart from an operation's fork at the same column, as an
        index's in ``if s[0] == "q":``, so one never makes the other's side old.
        """
        return (key[1], fork.raising, not fork.taken) not in self._sides

    def untried(self) -> dict[ForkSite, int]:
        """How many forks at each site are still open: no input aimed at them, no other side ran.

        A fork that paths share is one fork, counted once. It is read when
        the run stops, so a run that stopped early can say which forks it
        never tried.
        """
        still_open = {
            key: fork.raising
            for forks, keys, _ in self._paths
            for fork, key in zip(forks, keys, strict=True)
            if self._open(key, fork.taken)
        }
        # counted by site and kind, so a site's ForkSite is made once, not once a fork
        counts = Counter((key[1], raising) for key, raising in still_open.items())
        return {
            ForkSite(self._sites[number], raising): count
            for (number, raising), count in counts.items()
        }

    def _open(self, key: ForkKey, taken: bool) -> bool:
        """A fork no input aimed at, whose other side no input ran."""
        parent, site = key
        return key not in self._aimed and (parent, site, not taken) not in self._ids
