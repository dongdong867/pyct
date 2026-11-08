"""Where a condition's value came from, read backward through its function's local names."""

import sys
import textwrap
import types
from collections.abc import Mapping
from pathlib import Path

import pytest

from pyct.core.foundation.branch import Site
from pyct.results.causes import Source, SourceKind
from pyct.results.coverage import compiled
from pyct.results.graphs import OutOfTimeError
from pyct.results.sources import Origins


def module(tmp_path: Path, source: str) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(source))
    return str(file)


def code_named(file: str, name: str) -> types.CodeType:
    """The code of the function ``name`` in the module."""
    pending = [compiled(file)]
    while pending:
        code = pending.pop()
        if code.co_name == name:
            return code
        pending.extend(c for c in code.co_consts if isinstance(c, types.CodeType))
    raise LookupError(name)


def sources(
    file: str,
    function: str,
    at: tuple[int, int],
    lost: Mapping[tuple[int, int], tuple[str, ...]] | None = None,
) -> tuple[Source, ...]:
    origins = Origins(file, lost or {}, step=lambda: None)
    return origins.of(code_named(file, function), *at)


def loop(file: str, name: str, line: int, col: int) -> Source:
    return Source(SourceKind.LOOP, name, Site(file=file, line=line, col=col))


def lost(file: str, name: str, call: str, line: int, col: int) -> Source:
    return Source(SourceKind.LOST, name, Site(file=file, line=line, col=col), call)


COUNTS = """\
def counts(s):
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 25:
        return "many"
    return "few"
"""


def test_a_name_a_for_loop_changes_comes_from_that_loop(tmp_path: Path) -> None:
    file = module(tmp_path, COUNTS)

    assert sources(file, "counts", (6, 7)) == (loop(file, "t", 3, 4),)


WHILE = """\
def halves(n):
    k = 0
    m = n
    while m > 1:
        m = m // 2
        k = k + 1
    if k == 9:
        return 1
    return 0
"""


def test_a_name_a_while_loop_changes_comes_from_that_loop(tmp_path: Path) -> None:
    file = module(tmp_path, WHILE)

    assert sources(file, "halves", (7, 7)) == (loop(file, "k", 4, 4),)


THROUGH = """\
def through(s):
    t = 0
    for c in s:
        t += 1
    u = t * 2
    v = u
    if v > 40:
        return 1
    return 0
"""


def test_the_reading_follows_names_back_to_the_loop(tmp_path: Path) -> None:
    file = module(tmp_path, THROUGH)

    assert sources(file, "through", (7, 7)) == (loop(file, "t", 3, 4),)


COMPREHENSION = """\
def counted(s):
    t = sum(1 for c in s if c == "z")
    if t > 25:
        return 1
    if len([c for c in s if c == "y"]) > 3:
        return 2
    return 0
"""


def test_a_comprehension_counts_as_a_loop(tmp_path: Path) -> None:
    file = module(tmp_path, COMPREHENSION)

    assert sources(file, "counted", (3, 7)) == (loop(file, "t", 2, 11),)
    # in the condition itself, the comprehension is named by the name it reads first
    assert sources(file, "counted", (5, 7)) == (loop(file, "s", 5, 11),)


BIN = """\
def ones(x):
    if bin(x).count("1") == 7:
        return 1
    y = bin(x)
    if y.count("0") == 3:
        return 2
    return 0
"""


def test_a_call_that_recorded_a_downgrade_is_where_the_value_was_lost(tmp_path: Path) -> None:
    file = module(tmp_path, BIN)
    downgrades = {(2, 7): ("bin",), (4, 8): ("bin",)}

    assert sources(file, "ones", (2, 7), downgrades) == (lost(file, "x", "bin", 2, 7),)
    assert sources(file, "ones", (5, 7), downgrades) == (lost(file, "x", "bin", 4, 8),)


OPERATOR = """\
def big(x):
    c = x ^ 0
    if c > 10:
        return 1
    return 0
"""


def test_an_operator_s_downgrade_is_where_the_value_was_lost(tmp_path: Path) -> None:
    file = module(tmp_path, OPERATOR)

    found = sources(file, "big", (3, 7), {(2, 8): ("__xor__",)})

    assert found == (lost(file, "x", "__xor__", 2, 8),)


def test_a_call_with_no_downgrade_at_its_site_is_read_through(tmp_path: Path) -> None:
    file = module(tmp_path, BIN)

    # the downgrade at the site is another call's, so neither call written there lost x
    assert sources(file, "ones", (2, 7), {(2, 7): ("encode",)}) == ()


def test_a_method_s_downgrade_names_the_value_its_receiver_reads(tmp_path: Path) -> None:
    file = module(tmp_path, BIN)

    found = sources(file, "ones", (2, 7), {(2, 7): ("count",)})

    assert found == (lost(file, "x", "count", 2, 7),)


BOTH = """\
def both(x, s):
    t = 0
    for c in s:
        t += 1
    m = x.bit_length()
    if t + m > 30:
        return 1
    return 0
"""


def test_each_source_found_is_listed_in_code_order(tmp_path: Path) -> None:
    file = module(tmp_path, BOTH)

    found = sources(file, "both", (6, 7), {(5, 8): ("bit_length",)})

    assert found == (loop(file, "t", 3, 4), lost(file, "x", "bit_length", 5, 8))


ELSEWHERE = """\
LIMIT = 3


class Box:
    def __init__(self):
        self.count = 0

    def full(self, x):
        n = self.count
        if n > LIMIT:
            return 1
        if x > 4:
            return 2
        return 0


def outer(s):
    t = 0

    def inner():
        for c in s:
            t = 1
        return t

    if t > 2:
        return 1
    return 0
"""


@pytest.mark.parametrize(
    ("function", "at"),
    [
        pytest.param("full", (10, 11), id="an attribute and a global"),
        pytest.param("full", (12, 11), id="a parameter"),
        pytest.param("outer", (25, 7), id="another function's local"),
    ],
)
def test_a_value_from_outside_the_function_s_local_names_gives_no_source(
    tmp_path: Path, function: str, at: tuple[int, int]
) -> None:
    file = module(tmp_path, ELSEWHERE)

    assert sources(file, function, at) == ()


def test_a_module_that_no_longer_reads_gives_no_source(tmp_path: Path) -> None:
    file = module(tmp_path, COUNTS)
    code = code_named(file, "counts")
    Path(file).write_text("def counts(:\n")

    assert Origins(file, {}, step=lambda: None).of(code, 6, 7) == ()


def test_the_reading_stops_when_the_analysis_s_stop_comes(tmp_path: Path) -> None:
    file = module(tmp_path, COUNTS)
    code = code_named(file, "counts")
    origins = Origins(file, {}, step=lambda: None)
    # the module is read once, so a later condition's steps are its reading's own
    origins.of(code, 6, 7)
    origins.step = stop

    with pytest.raises(OutOfTimeError):
        origins.of(code, 6, 7)


def test_each_walk_of_the_reading_takes_steps(tmp_path: Path) -> None:
    file = module(tmp_path, COUNTS)
    code = code_named(file, "counts")
    walks: list[str] = []
    origins = Origins(file, {}, step=lambda: walks.append(sys._getframe(1).f_code.co_name))

    origins.of(code, 6, 7)
    first = set(walks)
    walks.clear()
    origins.of(code, 6, 7)

    # the module's functions and each one's bindings are read once; the condition's test and its
    # names, for each condition
    reading = {"_own_nodes", "sources", "_read"}
    assert {"_function", "_with_loops", *reading} <= first
    assert set(walks) == reading


def stop() -> None:
    raise OutOfTimeError


NAMED = """\
def powered(x):
    base = 2
    if pow(base, x) == 64:
        return 1
    n = 7
    if n ^ x == 3:
        return 2
    return 0
"""


def test_a_lost_source_names_the_value_that_went_in_tracked(tmp_path: Path) -> None:
    file = module(tmp_path, NAMED)
    downgrades = {(3, 7): ("pow",), (6, 7): ("__rxor__",)}

    assert sources(file, "powered", (3, 7), downgrades) == (lost(file, "x", "pow", 3, 7),)
    assert sources(file, "powered", (6, 7), downgrades) == (lost(file, "x", "__rxor__", 6, 7),)


COMPREHENSION_TEST = """\
def picks(x):
    return [
        c
        for c in bin(x)
        if c == "z"
    ]
"""


def test_a_comprehension_s_own_name_comes_from_the_comprehension(tmp_path: Path) -> None:
    file = module(tmp_path, COMPREHENSION_TEST)

    assert sources(file, "picks", (5, 11)) == (loop(file, "c", 2, 11),)
