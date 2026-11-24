"""The one slot through which an operation pyct has not taught hands its loss on, to the recording
of loss runs (`pyct.core.entry.losses`), which hands back what the target gets: the answer, or,
at a loss site in use, the answer tracked (`pyct.core.entry.calls_in_use`). That recording fills
it while an input that records them is live, since foundation may not import entry, and empties
it when the input ends."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.foundation.branch import Downgrade

# what the slot holds: called with the downgrade, the operation's operands, the tracked receiver
# first, and the real answer; it hands back what the target gets
type Hears = Callable[[Downgrade, tuple[object, ...], object], object]

HEARS: list[Hears | None] = [None]
