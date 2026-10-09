"""One call's facts, kept as they happen, and the watch told each one.

A call's forks, downgrades and lines used to be read after the call
returned. A call that runs in a process of its own can die before that,
so each fact is kept, and handed to a watch, the moment it happens: what
the watch already holds survives the process.
"""

from __future__ import annotations

from typing import Protocol

from pyct.core import escapes
from pyct.core.branch import Branch, Downgrade, Fact, SinkItem, Site
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount

# the tally of the call running now in this process, if one is
_LIVE: list[Tally | None] = [None]

# the most forks one call's path keeps. Past it the call's line ends `too_long`, as its own: a
# line lists its forks whole, and the README's isolation rule ends a run within 1.5 s of its
# deadline for a line of 200,000 forks
MOST_FORKS = 200_000


def too_long() -> Failure:
    """The ending of a call whose path went past ``MOST_FORKS``, however the target ended it.

    Its line lists only the forks before the bound, so what came after, its
    own ending included, is not the path the line shows.
    """
    detail = f"the input took more than {MOST_FORKS} forks, the most pyct keeps for one input"
    return Failure(kind=FailureKind.TOO_LONG, detail=detail)


class Watch(Protocol):
    """Who hears each fact of one call, the moment the call makes it.

    A fork as it is taken, a fact as the path comes to hold it, and a line the
    first time the call reaches it. A downgrade comes with its site and its
    count so far: a count of 1 starts an entry, and a higher count means the
    last entry grew by one. The tally decides what an entry is; a watch only
    mirrors it.
    """

    def fork(self, branch: Branch) -> None: ...

    def fact(self, fact: Fact) -> None: ...

    def line(self, number: int) -> None: ...

    def downgrade(self, name: str, site: Site, count: int) -> None: ...


class Tally:
    """What one call did so far: its lines, its forks, its facts and its downgrades, in call order.

    It is the call's sink, so core pushes forks and downgrades into it, and
    the line tracer feeds it lines. Consecutive downgrades of one name at one
    site collapse into one entry as they arrive; a fork between them does not
    split them, because the entries run over the downgrades alone, as the line
    lists them. After the call it is sealed: pyct's own text calls on a tracked
    value, such as writing the failure, are not the target's and record
    nothing.

    Once the call has taken ``MOST_FORKS`` forks it is ``past_bound``: it
    keeps no fork or fact after them, and tells the watch of none, while the
    lines and downgrades the call reaches are still kept.
    """

    def __init__(self, watch: Watch | None = None) -> None:
        self.lines: set[int] = set()
        self.branches: list[Branch] = []
        # each fact as the path came to hold it, placed after the forks recorded before it
        self.facts: list[Fact] = []
        self.watch = watch
        self.sealed = False
        self.past_bound = False
        # each entry one object, so the deadline landing between two steps can lose a call,
        # never pair a name with another entry's count
        self._entries: list[_Entry] = []

    def append(self, item: SinkItem, /) -> None:
        """Keep a fork, a fact or a downgrade the call just made. The ``BranchSink`` core pushes to.

        A sealed tally keeps nothing. A value the target kept from this call can still reach it
        from a later call in the same process, and that call's condition is then lost: the
        call running now names it, a fork by the operation that took it: a truth test's `__bool__`,
        a walk's `__iter__`, an index's `__getitem__`.
        """
        if self.sealed:
            live = _LIVE[0]
            # a place names no check the target ran, so it names no loss
            placed = isinstance(item, Fact) and not item.decided
            if live is not None and live is not self and not placed:
                name = item.name if isinstance(item, Downgrade) else item.lost_as
                live.append(Downgrade(name=name, site=item.site))
            return
        if self.past_bound and not isinstance(item, Downgrade):
            return
        if isinstance(item, Branch):
            if len(self.branches) == MOST_FORKS:
                self.past_bound = True
                return
            self.branches.append(item)
            if self.watch is not None:
                self.watch.fork(item)
            return
        if isinstance(item, Fact):
            self._fact(item)
            return
        self._downgrade(item.name, item.site)

    def _fact(self, fact: Fact) -> None:
        """Keep a fact, placed after the forks recorded so far, and tell the watch."""
        placed = fact.placed_after(len(self.branches))
        self.facts.append(placed)
        if self.watch is not None:
            self.watch.fact(placed)

    def line(self, number: int) -> None:
        """Keep a line the call reached. Only its first sight reaches the watch."""
        if number in self.lines:
            return
        self.lines.add(number)
        if self.watch is not None:
            self.watch.line(number)

    def go_live(self) -> None:
        """Make this the tally of the call running now, which a value from a call that is over
        names its loss to. The walk keys an earlier call handed out are no keys of its path."""
        _LIVE[0] = self
        escapes.forget()

    def seal(self) -> None:
        """End the call's tally: whatever comes after is pyct's, not the target's."""
        self.sealed = True
        if _LIVE[0] is self:
            _LIVE[0] = None

    def counted(self) -> tuple[DowngradeCount, ...]:
        """The downgrades as the line lists them, one entry per run of one name at one site."""
        return tuple(
            DowngradeCount(name=entry.name, count=entry.count, site=entry.site)
            for entry in self._entries
        )

    def _downgrade(self, name: str, site: Site) -> None:
        last = self._entries[-1] if self._entries else None
        # a site found again is the one object caller_site keeps, so `is` settles most repeats
        if last is not None and last.name == name and (last.site is site or last.site == site):
            last.count += 1
        else:
            self._entries.append(_Entry(name, site))
        if self.watch is not None:
            self.watch.downgrade(name, site, self._entries[-1].count)


class _Entry:
    """One run of calls of one name at one site, counted as they come."""

    __slots__ = ("count", "name", "site")

    def __init__(self, name: str, site: Site) -> None:
        self.name = name
        self.site = site
        self.count = 1
