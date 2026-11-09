"""The end of a walk: every tuple built and every value held back copied, each once, and each
put everywhere the walk put it.

A held-back value is copied by deepcopy in a frame of its own, whose memo
reads the frame it was started in, so a copy started inside another sees
every copy under way. What a frame makes joins the frame it runs in when it
ends, and is undone when its copy is refused.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pyct.binding.copies import Scratch
from pyct.binding.tuples import (
    PlainCopy,
    TupleBuild,
    held_among,
    innermost_first,
    put,
    tuples_among,
)


class _CycleError(Exception):
    """A tuple a held-back value's copy reached holds a value whose copy is under way and has
    not begun, so deepcopy would close the cycle with a tuple of its own."""

    def __init__(self, plain: PlainCopy) -> None:
        super().__init__()
        self.plain = plain


@dataclass(eq=False)
class _Frame:
    """One held-back value's copy under way: its memo, and each tuple and copy made inside
    it."""

    plain: PlainCopy
    scratch: Scratch
    made: list[TupleBuild | PlainCopy] = field(default_factory=list)


class Finish:
    """The end of one walk, over the walk's copies, which it adds each built tuple and each
    copy to, and the tuples it noted, by the identity of each seed tuple and each item list."""

    def __init__(
        self,
        copies: dict[int, object],
        kept: list[object],
        tuples: Mapping[int, TupleBuild],
        owners: Mapping[int, TupleBuild],
    ) -> None:
        self._copies = copies
        self._kept = kept
        self._tuples = tuples
        self._owners = owners
        # the tuples and values held back among each tuple's items, and each held-back value's
        # copy under way, innermost last
        self._inside: dict[int, list[TupleBuild]] = {}
        self._among: dict[int, list[PlainCopy]] = {}
        self._frames: list[_Frame] = []

    def run(self, plain: Iterable[PlainCopy]) -> None:
        """Build every tuple and copy every value held back: each tuple after every tuple and
        value held back among its items (see ``_build``), and each held-back value no tuple
        holds last."""
        held = list(plain)
        builds = list(self._tuples.values())
        self._inside = tuples_among(builds, self._owners)
        self._among = held_among(held, self._owners)
        for build in innermost_first(builds, self._inside):
            self._build(build)
        for each in held:
            self._copy_whole(each)

    def _build(self, build: TupleBuild) -> None:
        """Build a tuple, once, after the values held back and the tuples among its items, and
        put it everywhere the walk put it.

        ``tuple.__new__`` builds it, so a namedtuple's own constructor does
        not run. A held-back value whose copy is under way goes in as the copy
        deepcopy has begun (see ``_take_begun``). A tuple built while its
        insides were is not built again.
        """
        if build.made is not None:
            return
        for plain in self._among.get(id(build), ()):
            if plain.copying:
                self._take_begun(plain, build)
            else:
                self._copy_whole(plain)
        for inner in self._inside.get(id(build), ()):
            self._build(inner)
        if build.made is not None:
            return
        build.made = tuple.__new__(type(build.value), build.items)
        self._note(id(build.value), build.made, build)
        for into, slot in build.placements:
            put(into, slot, build.made, build.value)

    def _take_begun(self, plain: PlainCopy, build: TupleBuild) -> None:
        """Put into a tuple's items the copy deepcopy has begun of a held-back value under way,
        which it fills once the tuple is built.

        When that value's copy, or one started inside it, has not begun, a
        deque's copy say, which deepcopy makes before it copies what it holds,
        but a bound method's, which it makes after, that copy closes a cycle
        deepcopy would close with a tuple of its own: it is refused
        (``_CycleError``).
        """
        at = next(at for at, frame in enumerate(self._frames) if frame.plain is plain)
        for frame in self._frames[at:]:
            if not dict.__contains__(frame.scratch, id(frame.plain.value)):
                raise _CycleError(frame.plain)
        begun = dict.__getitem__(self._frames[at].scratch, id(plain.value))
        for into, slot in plain.placements:
            if into is build.items:
                put(into, slot, begun, plain.value)

    def _copy_whole(self, plain: PlainCopy) -> None:
        """Copy a held-back value, once, in a frame of its own, and put the copy everywhere the
        walk put it.

        Its deepcopy reads the copies of the frames it runs in and the walk's,
        and builds a tuple it reaches that is not built yet. A copy deepcopy
        refuses, or that closes a cycle, leaves the value as it came, and what
        its frame made is undone, to be made again over the value.
        """
        if plain.done or plain.copying:
            return
        made = self._copied_in_a_frame(plain)
        plain.made, plain.done = made, True
        self._note(id(plain.value), made, plain)
        for into, slot in plain.placements:
            put(into, slot, made, plain.value)

    def _copied_in_a_frame(self, plain: PlainCopy) -> object:
        """A held-back value's deepcopy, made in a frame of its own, or the value itself when
        deepcopy refuses it or it closes a cycle; a cycle another value closes ends this copy
        too, and goes on to that value's."""
        plain.copying = True
        under = self._frames[-1].scratch if self._frames else self._copies
        frame = _Frame(plain, Scratch(under, self._built_on_demand))
        self._frames.append(frame)
        try:
            made = copy.deepcopy(plain.value, frame.scratch)
        except _CycleError as error:
            self._ended(frame, joined=False)
            if error.plain is not plain:
                raise
            return plain.value
        except Exception:
            self._ended(frame, joined=False)
            return plain.value
        self._ended(frame, joined=True)
        return made

    def _ended(self, frame: _Frame, *, joined: bool) -> None:
        """End a held-back value's copy: what its frame made joins the frame it ran in, or is
        undone."""
        self._frames.pop()
        frame.plain.copying = False
        if not joined:
            for each in frame.made:
                if isinstance(each, TupleBuild):
                    each.made = None
                else:
                    each.done, each.made = False, None
            return
        scratch = frame.scratch
        self._kept.extend(scratch.pop(id(scratch), []))
        for key, made in scratch.items():
            self._note(key, made, None)
        if self._frames:
            self._frames[-1].made.extend(frame.made)

    def _note(self, key: int, made: object, maker: TupleBuild | PlainCopy | None) -> None:
        """Note a copy in the memo the copy under way reads, or the walk's, with what made it,
        undone with that copy's frame."""
        if not self._frames:
            self._copies[key] = made
            return
        frame = self._frames[-1]
        dict.__setitem__(frame.scratch, key, made)
        if maker is not None:
            frame.made.append(maker)

    def _built_on_demand(self, key: int) -> object | None:
        """The tuple a held-back value's deepcopy reaches, built now; None for one the walk
        does not build."""
        build = self._tuples.get(key)
        if build is None:
            return None
        self._build(build)
        return build.made
