"""The end of a walk: every tuple built and every value held back copied, each once, and each
put everywhere the walk put it."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping

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
    """A held-back value's deepcopy reached a tuple that holds that value, before it began the
    value's own copy."""


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
        self._copying: list[tuple[PlainCopy, Scratch]] = []

    def run(self, plain: Iterable[PlainCopy]) -> None:
        """Build every tuple and copy every value held back, each once, now that every path is
        walked: each tuple after every tuple and value held back among its items (see
        ``_build``), and each held-back value no tuple holds last."""
        held = list(plain)
        builds = list(self._tuples.values())
        self._inside = tuples_among(builds, self._owners)
        self._among = held_among(held, self._owners)
        for build in innermost_first(builds, self._inside):
            self._build(build)
        for each in held:
            self._copy_whole(each)

    def _build(self, build: TupleBuild) -> bool:
        """Build a tuple, once, after the values held back and the tuples among its items, and
        put it everywhere the walk put it; False when it cannot be built yet.

        ``tuple.__new__`` builds it, so a namedtuple's own constructor does
        not run. A held-back value whose copy is under way, a deque that holds
        this tuple say, goes in as the copy deepcopy has begun, which it fills
        once this tuple is built; when deepcopy has begun none, this tuple
        waits for that copy to end.
        """
        if build.made is not None:
            return True
        for plain in self._among.get(id(build), ()):
            if not self._copy_whole(plain) and not self._begun(plain, build):
                return False
        if build.made is not None or not all(map(self._build, self._inside.get(id(build), ()))):
            return build.made is not None
        made = tuple.__new__(type(build.value), build.items)
        build.made = made
        self._copies[id(build.value)] = made
        for into, slot in build.placements:
            put(into, slot, made, build.value)
        return True

    def _begun(self, plain: PlainCopy, build: TupleBuild) -> bool:
        """Put the copy deepcopy has begun of a held-back value among a tuple's items, and note
        the tuple used it; False when deepcopy has begun none."""
        for each, scratch in reversed(self._copying):
            if each is plain and dict.__contains__(scratch, id(plain.value)):
                begun = dict.__getitem__(scratch, id(plain.value))
                for into, slot in plain.placements:
                    if into is build.items:
                        put(into, slot, begun, plain.value)
                plain.used_by.append(build)
                return True
        return False

    def _copy_whole(self, plain: PlainCopy) -> bool:
        """Copy a held-back value, once, and put the copy everywhere the walk put it; False
        while its copy is under way.

        Its deepcopy reads the walk's copies, and builds a tuple it reaches
        that is not built yet. A copy deepcopy refuses leaves the value as it
        came, and each tuple built with the copy it had begun is built again
        holding the value.
        """
        if plain.done or plain.copying:
            return plain.done
        plain.copying = True
        scratch = Scratch(self._copies, self._built_on_demand)
        self._copying.append((plain, scratch))
        try:
            made = copy.deepcopy(plain.value, scratch)
        except Exception:
            made = None
        finally:
            self._copying.pop()
        if made is None:
            made = plain.value
        else:
            self._kept.extend(scratch.pop(id(scratch), []))
            self._copies.update(scratch)
        plain.made, plain.done, plain.copying = made, True, False
        self._place_whole(plain)
        return True

    def _place_whole(self, plain: PlainCopy) -> None:
        """Put a held-back value's copy everywhere the walk put it, and build again each tuple
        built with a copy deepcopy began and then refused."""
        if plain.made is not plain.value:
            self._copies[id(plain.value)] = plain.made
            self._kept.append(plain.value)
        for into, slot in plain.placements:
            put(into, slot, plain.made, plain.value)
        for build in plain.used_by if plain.made is plain.value else ():
            build.made = None
            self._build(build)

    def _built_on_demand(self, key: int) -> object | None:
        """The tuple a held-back value's deepcopy reaches, built now, or None for one the walk
        does not build.

        A tuple that cannot be built yet holds a value held back whose copy is
        under way and not begun, so the two make a cycle deepcopy would close
        with a tuple of its own: that copy is refused, and the value is handed
        on as it came to every place that holds it.
        """
        build = self._tuples.get(key)
        if build is None:
            return None
        if not self._build(build):
            raise _CycleError
        return build.made
