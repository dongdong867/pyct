"""The input a path's program is written from, and how it is written for it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pyct.binding.shapes import DictShape, ListShape
from pyct.core.branch import Expression

# the steps one read takes before its program is written again with its clamps settled: far
# more than a read through a list changed at plain positions takes, and far less than one that
# doubles with each cut
READ_STEPS = 512


@dataclass(frozen=True)
class Origin:
    """The input whose path this is: each tracked list and dict with its shape, each leaf's
    value, and how the program is written for it.

    ``settle`` names the list parts whose clamps, where the path leaves them open, go the way
    they went there (see ``list_slices``), and ``everywhere`` settles every one. ``hold`` says
    whether a list the target repeats holds the answer's lengths (see ``_repeated``), and
    ``bounded`` whether each bound a form is exact inside is held (see ``render._bounded``).
    ``steps`` is the most steps one read takes before its program is written again settled,
    None for no limit; ``most`` the most all reads of the program take together before the
    program is given up (``ProgramTooLargeError``), None for no limit; and ``until`` the
    monotonic instant writing must end by. ``keep`` says whether each dict keeps the input's
    keys no fork names and makes none up, and each list of mixed kinds its length at least,
    ``pinned`` whether each dict keeps each key a walk read at its place, and ``lookups`` the most
    steps a path's tracked-key lookups take together before the program is given up, None for no
    limit (see ``dicts``). ``places`` are the places the
    path's facts keep: which key a walk read where (see ``core.dict_reads.placed``).
    ``fixed_reads`` says whether a piece of a split read from its end, where no walk of the
    reversed string reads it, holds the string to the count c* (see ``split_lists``).
    """

    shapes: Mapping[str, ListShape] = field(default_factory=dict)
    dicts: Mapping[str, DictShape] = field(default_factory=dict)
    values: Mapping[str, object] = field(default_factory=dict)
    settle: frozenset[int] = frozenset()
    everywhere: bool = False
    hold: bool = True
    bounded: bool = True
    steps: int | None = READ_STEPS
    most: int | None = None
    until: float | None = None
    keep: bool = True
    pinned: bool = True
    lookups: int | None = None
    places: tuple[Expression, ...] = ()
    fixed_reads: bool = True
