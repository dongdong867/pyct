"""A walk over a tracked str: one fork a pass at the line where the walk runs, and each
character a tracked str, as indexing hands it out, with no long-enough fork of its own."""

import pytest

from pyct.core.branch import Branch, Downgrade, Expression, SinkItem, Site
from pyct.core.strs import ConcolicStr

# a probe whose text is fixed here, so the line and column of each fork are exact. Each walk
# gathers what it hands out, so the test reads the characters back
PROBE = """\
def loop(s):
    out = []
    for c in s:
        out.append(c)
    return out

def comprehension(s):
    return [c for c in s]

def listed(s):
    return list(s)

def first(s):
    for c in s:
        return [c]
    return []

def zipped(s, t):
    return [pair for pair in zip(s, t)]

def numbered(s):
    return [c for _, c in enumerate(s)]
"""


def _walked(name: str, *args: object) -> list[object]:
    """What the probe function ``name`` gathers from its walk of ``args``."""
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace[name]
    assert callable(probe)
    handed = probe(*args)
    assert isinstance(handed, list)
    return handed


def _tracked(value: str, sink: list[SinkItem], name: str = "s") -> ConcolicStr:
    return ConcolicStr(value, expression=name, sink=sink)


def _pass(at: int, taken: bool, line: int = 3, col: int = 13, name: str = "s") -> Branch:
    """The fork a walk records for position ``at`` of the string named ``name``."""
    fork: Expression = [">", ["len", name], at]
    return Branch(expression=fork, taken=taken, site=Site(file="<probe>", line=line, col=col))


def test_a_loop_records_a_fork_a_pass_and_its_exit_at_the_iterables_column() -> None:
    sink: list[SinkItem] = []

    _walked("loop", _tracked("ab", sink))

    # `    for c in s:`: Python places the loop's step at the iterable, column 13
    assert sink == [_pass(0, True), _pass(1, True), _pass(2, False)]


def test_each_character_is_a_tracked_str_carrying_its_index() -> None:
    sink: list[SinkItem] = []

    handed = _walked("loop", _tracked("ab", sink))

    assert [(str.__str__(c), c.expression) for c in handed if isinstance(c, ConcolicStr)] == [
        ("a", ["[]", "s", 0]),
        ("b", ["[]", "s", 1]),
    ]
    assert all(isinstance(c, ConcolicStr) and c.sink is sink for c in handed)


def test_the_empty_string_records_only_the_exit() -> None:
    sink: list[SinkItem] = []

    handed = _walked("loop", _tracked("", sink))

    assert handed == []
    assert sink == [_pass(0, False)]


def test_a_walk_that_stops_early_records_only_the_passes_it_asked_for() -> None:
    sink: list[SinkItem] = []

    _walked("first", _tracked("abc", sink))

    assert sink == [_pass(0, True, line=14, col=13)]


def test_a_walk_of_a_piece_measures_the_piece() -> None:
    sink: list[SinkItem] = []
    piece = _tracked("abc", sink)[1:]

    handed = _walked("loop", piece)

    sliced: Expression = ["[:]", "s", 1, None]
    assert [item.expression for item in sink if isinstance(item, Branch)] == [
        [">", ["len", sliced], 0],
        [">", ["len", sliced], 1],
        [">", ["len", sliced], 2],
    ]
    assert [c.expression for c in handed if isinstance(c, ConcolicStr)] == [
        ["[]", sliced, 0],
        ["[]", sliced, 1],
    ]


# each other walk in the probe: its name, and the line and column of the fork it records. A
# comprehension's step sits at its iterable, the `enumerate(s)` call included, and a call that
# walks s itself at the call
WALKS: dict[str, tuple[int, int]] = {
    "comprehension": (8, 23),
    "listed": (11, 11),
    "numbered": (22, 26),
}


@pytest.mark.parametrize(("name", "site"), WALKS.items(), ids=list(WALKS))
def test_every_walk_records_the_same_forks_where_it_runs(name: str, site: tuple[int, int]) -> None:
    sink: list[SinkItem] = []
    line, col = site

    handed = _walked(name, _tracked("ab", sink))

    forks = [item for item in sink if isinstance(item, Branch)]
    assert forks == [_pass(at, at < 2, line=line, col=col) for at in range(3)]
    assert [c.expression for c in handed if isinstance(c, ConcolicStr)] == [
        ["[]", "s", 0],
        ["[]", "s", 1],
    ]


def test_zip_walks_both_strings_a_pass_at_a_time() -> None:
    sink: list[SinkItem] = []

    _walked("zipped", _tracked("ab", sink), _tracked("xyz", sink, name="t"))

    # zip asks s first, and a pass s ends asks t nothing more
    assert sink == [
        _pass(0, True, line=19, col=29),
        _pass(0, True, line=19, col=29, name="t"),
        _pass(1, True, line=19, col=29),
        _pass(1, True, line=19, col=29, name="t"),
        _pass(2, False, line=19, col=29),
    ]


def test_list_asks_for_the_length_first_as_python_does() -> None:
    sink: list[SinkItem] = []

    _walked("listed", _tracked("ab", sink))

    # list sizes itself by `__len__` before it walks, and pyct has not taught `len(s)`
    assert sink[0] == Downgrade(name="__len__")
