"""One call's facts, kept as they happen, and the watch told each one.

A call's forks, downgrades and lines used to be read after the call
returned. A call that runs in a process of its own can die before that,
so each fact is kept, and handed to a watch, the moment it happens: what
the watch already holds survives the process.
"""

from __future__ import annotations

from typing import Protocol

from pyct.core.branch import Branch, SinkItem
from pyct.results.record import DowngradeCount


class Watch(Protocol):
    """Who hears each fact of one call, the moment the call makes it.

    A fork as it is taken, and a line the first time the call reaches it. A
    downgrade comes with its count so far: a count of 1 starts an entry, and a
    higher count means the last entry grew by one. The tally decides what an
    entry is; a watch only mirrors it.
    """

    def fork(self, branch: Branch) -> None: ...

    def line(self, number: int) -> None: ...

    def downgrade(self, name: str, count: int) -> None: ...


class Tally:
    """What one call did so far: its lines, its forks, and its downgrades, in call order.

    It is the call's sink, so core pushes forks and downgrades into it, and
    the line tracer feeds it lines. Consecutive downgrades of one name
    collapse into one entry as they arrive; a fork between them does not split
    them, because the entries run over the downgrades alone, as the line lists
    them. After the call it is sealed: pyct's own text calls on a tracked
    value, such as writing the failure, are not the target's and record
    nothing.
    """

    def __init__(self, watch: Watch | None = None) -> None:
        self.lines: set[int] = set()
        self.branches: list[Branch] = []
        self.watch = watch
        self.sealed = False
        self._names: list[str] = []
        self._counts: list[int] = []

    def append(self, item: SinkItem, /) -> None:
        """Keep a fork or a downgrade the call just made. The ``BranchSink`` core pushes to."""
        if self.sealed:
            return
        if isinstance(item, Branch):
            self.branches.append(item)
            if self.watch is not None:
                self.watch.fork(item)
            return
        self._downgrade(item.name)

    def line(self, number: int) -> None:
        """Keep a line the call reached. Only its first sight reaches the watch."""
        if number in self.lines:
            return
        self.lines.add(number)
        if self.watch is not None:
            self.watch.line(number)

    def seal(self) -> None:
        """End the call's tally: whatever comes after is pyct's, not the target's."""
        self.sealed = True

    def counted(self) -> tuple[DowngradeCount, ...]:
        """The downgrades as the line lists them, one entry per run of one name."""
        return tuple(
            DowngradeCount(name=name, count=count)
            for name, count in zip(self._names, self._counts, strict=True)
        )

    def _downgrade(self, name: str) -> None:
        if self._names and self._names[-1] == name:
            self._counts[-1] += 1
        else:
            self._names.append(name)
            self._counts.append(1)
        if self.watch is not None:
            self.watch.downgrade(name, self._counts[-1])
