"""Every fork, fact and downgrade a loop's formula records sits at the loop's place: the formula is
not code of the target, and no line of it is one the target holds."""

import math
from collections.abc import Callable, Mapping

from pyct.binding.bind import bind
from pyct.core.entry import bound
from pyct.core.entry.in_use import LoopInUse
from pyct.core.entry.math_calls import ROUTERS
from pyct.core.foundation.branch import Branch, Downgrade, Fact, PieceRun, SinkItem, Site
from tests.unit.core.entry.test_in_use import using
from tests.unit.core.entry.test_pieces import FILE, hooked

READS = """\
def f(s, d, x):
    t = 0
    for c in s:
        t += 1
        g(d, x)
    return t
"""
LOOP = (3, 4)
NAMES = ("d", "s", "t", "x")

type Records = list[tuple[str, object, Site]]


def recorded_by(formula: Callable[[Mapping[str, object]], object]) -> Records:
    """Each fork, fact and downgrade an input records when READS's loop is in use with a formula
    that calls ``formula`` on the values going in and gives the loop's own count: its kind, its
    condition or name, and its site."""

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        formula(values)
        s, t = values["s"], values["t"]
        assert isinstance(s, str)
        assert isinstance(t, int)
        return {"t": t + str.__len__(s)}

    f = hooked(READS)
    sink: list[SinkItem]
    with using({LOOP: LoopInUse(NAMES, ("t",), counting)}) as sink:
        f(**bind({"s": "ab", "d": {"a": 2}, "x": 5.0}, sink))
    return [_record(each) for each in sink if type(each) is not PieceRun]


def _record(item: SinkItem) -> tuple[str, object, Site]:
    if isinstance(item, Downgrade):
        return ("downgrade", item.name, item.site)
    assert isinstance(item, Branch | Fact)
    return (type(item).__name__.lower(), item.expression, item.site)


AT_LOOP = Site(FILE, *LOOP)


def test_a_fact_the_formula_s_truth_test_records_is_placed_at_the_loop() -> None:
    def proven(values: Mapping[str, object]) -> None:
        if bound.len(values["s"]) >= 0:
            return

    assert recorded_by(proven) == [("fact", [">=", ["len", "s"], 0], AT_LOOP)]


def test_a_formula_s_reads_of_a_dict_going_in_are_placed_at_the_loop() -> None:
    def reads(values: Mapping[str, object]) -> None:
        d = values["d"]
        assert isinstance(d, dict)
        assert d["a"] == d["a"]

    assert recorded_by(reads)[:2] == [
        ("branch", ["in", "'a'", "d"], AT_LOOP),
        ("fact", ["in", "'a'", "d"], AT_LOOP),
    ]
    assert {site for _, _, site in recorded_by(reads)} == {AT_LOOP}


def test_a_downgrade_through_math_in_the_formula_is_placed_at_the_loop() -> None:
    def logged(values: Mapping[str, object]) -> None:
        ROUTERS[id(math.log)](values["x"])

    assert recorded_by(logged) == [("downgrade", "log", AT_LOOP)]
