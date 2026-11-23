"""A fork that reads a value a loop's formula gave, or that the formula's own code records, is
marked ``summary`` (`pyct.core.entry.in_use.summed`); every other fork is handed back as it is."""

from collections.abc import Mapping

import pytest

from pyct.core.entry import in_use, pieces
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch, Expression, SinkItem, Site
from tests.unit.core.entry.test_in_use import LOOP, Formula, counted, tracked, using
from tests.unit.core.entry.test_pieces import FILE, hooked

AROUND = """\
def f(s):
    if s == "q":
        return 0, "q"
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 3:
        return t, "many"
    if s == "r":
        return t, "r"
    return t, "few"
"""
# the loop of AROUND
AT = (5, 4)


class Marking(list[SinkItem]):
    """A sink that marks each fork as the tally does, as it comes."""

    def append(self, item: SinkItem, /) -> None:
        super().append(in_use.summed(item) if type(item) is Branch else item)


def marked(source: str, at: tuple[int, int], formula: Formula, s: str) -> list[tuple[int, bool]]:
    """Each fork of the source's `f` on ``s``, with its loop in use, as the line it sits at and
    whether `summed` marked it as it came."""
    return marked_with(source, {at: LoopInUse(("s", "t"), ("t",), formula)}, s)


def marked_with(
    source: str, loops: Mapping[tuple[int, int], LoopInUse], s: str
) -> list[tuple[int, bool]]:
    """As `marked`, with each loop at its line and column in use."""
    f = hooked(source)
    sink = Marking()
    in_use.IN_USE.update({(FILE, *at): loop for at, loop in loops.items()})
    pieces.start(sink, alone=True)
    try:
        f(tracked(s, "s", sink))
    finally:
        pieces.forget()
        in_use.IN_USE.clear()
    return [(each.site.line, each.summary) for each in sink if type(each) is Branch]


def test_a_fork_after_the_loop_that_reads_the_formula_s_value_is_marked() -> None:
    assert marked(AROUND, AT, counted, "ab") == [(2, False), (8, True), (10, False)]


def test_a_fork_the_formula_s_own_code_records_is_marked() -> None:
    def guarded(values: Mapping[str, object]) -> Mapping[str, object]:
        s, t = values["s"], values["t"]
        assert isinstance(s, str)
        assert isinstance(t, int)
        if s.count("z") > 5:
            return {"t": t + 5}
        return {"t": t + s.count("z")}

    assert marked(AROUND, AT, guarded, "ab") == [(2, False), (5, True), (8, True), (10, False)]


def test_a_fork_with_no_formula_value_in_the_input_is_handed_back_as_it_is() -> None:
    fork = Branch([">", "x", 3], True, Site("m.py", 1, 0))

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counted)}):
        assert in_use.summed(fork) is fork


def test_a_fork_after_a_dropped_formula_is_not_marked() -> None:
    def wrong(values: Mapping[str, object]) -> Mapping[str, object]:
        return {"t": 7}

    assert marked(AROUND, AT, wrong, "ab") == [(2, False), (10, False)]


TWICE = """\
def f(s):
    u = s + "x"
    for _ in range(2):
        t = 0
        for c in s:
            if c == "z":
                t += 1
        if u == "zzx":
            return t
    return t
"""
# the inner loop of TWICE, in use, which matches its formula on each pass of the outer one
INNER = (5, 8)


def test_a_part_found_clean_is_not_walked_again_after_a_later_match_in_the_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    walked = in_use._reads_a_formula
    known: list[bool] = []

    def watched(
        expression: Expression, reads: dict[int, list[Expression]], clean: set[int]
    ) -> bool:
        # each `u == "zzx"` is a new list; the term of `u` inside it is the same one
        assert isinstance(expression, list)
        known.append(id(expression[1]) in clean)
        return walked(expression, reads, clean)

    monkeypatch.setattr(in_use, "_reads_a_formula", watched)

    assert marked(TWICE, INNER, counted, "ab") == [(8, False), (8, False)]
    # the second `u == "zzx"` comes after the inner loop's second match, and `u` is known clean
    assert known == [False, True]


HANDED_BACK = """\
def f(s):
    t = s.count("z")
    u = t + 1
    n = 0
    for c in s:
        n += 1
    if u == 9:
        return n
    for c in s:
        if c == "y":
            t += 0
    if u > 3:
        return t
    return n
"""


def test_a_part_found_clean_that_holds_a_term_handed_back_is_walked_again() -> None:
    def letters(values: Mapping[str, object]) -> Mapping[str, object]:
        s, n = values["s"], values["n"]
        assert isinstance(s, str)
        assert isinstance(n, int)
        return {"n": n + s.count("a") + s.count("b")}

    def kept(values: Mapping[str, object]) -> Mapping[str, object]:
        return {"t": values["t"]}

    loops = {
        (5, 4): LoopInUse(("n", "s"), ("n",), letters),
        (9, 4): LoopInUse(("s", "t"), ("t",), kept),
    }

    # after the first loop's match, `u == 9` finds `u`'s term clean; the second loop's formula
    # then hands back `t`'s term, which `u`'s holds, so `u > 3` holds a formula's term
    assert marked_with(HANDED_BACK, loops, "ab") == [(7, False), (12, True)]
