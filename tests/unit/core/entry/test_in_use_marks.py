"""A fork that reads a value a loop's formula gave, or that the formula's own code records, is
marked ``summary`` (`pyct.core.entry.in_use.summed`); every other fork is handed back as it is."""

from collections.abc import Mapping

from pyct.core.entry import in_use, pieces
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch, SinkItem, Site
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
    f = hooked(source)
    sink = Marking()
    in_use.IN_USE[(FILE, *at)] = LoopInUse(("s", "t"), ("t",), formula)
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
