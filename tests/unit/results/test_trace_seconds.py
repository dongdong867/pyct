"""The trace says how long each ask took, sums the seconds by answer, and names the lines each
input covered first."""

from pyct.core.branch import Site
from pyct.results.record import Aim, InputRecord, Miss, MissWhy, Source, Stop, StopKind
from pyct.results.trace import render_miss, render_stop, render_trace
from tests.unit.results.test_trace import COVERAGE, stopped_with


def test_render_miss_ends_on_the_seconds_its_ask_took() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT, solver_seconds=1.23456)

    assert render_miss(miss) == "missed m.py:5:7 unsat after 1.235 s\n"


def test_render_trace_says_how_long_a_solver_input_s_ask_took_after_its_aim() -> None:
    aim = Aim(site=Site(file="m.py", line=5, col=7), position=0)
    record = InputRecord(
        args={"x": 2},
        forks=(),
        covered_lines=frozenset({6}),
        source=Source.SOLVER,
        aim=aim,
        solver_seconds=0.0126,
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[1:3] == ["aim m.py:5:7 at position 0", "asked in 0.013 s"]


def test_render_trace_names_the_lines_an_input_covered_first_after_its_covered_line() -> None:
    first = InputRecord(
        args={"x": 1}, forks=(), covered_lines=frozenset({5, 6}), first_covered=frozenset({6, 5})
    )
    none = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({5}))

    lines = render_trace(first, COVERAGE).splitlines()

    at = lines.index("covered 2 of 7 lines in m.py")
    assert lines[at + 1] == "first covered 5, 6 in m.py"
    assert not any(
        line.startswith("first covered") for line in render_trace(none, COVERAGE).splitlines()
    )


def test_render_stop_sums_the_seconds_of_the_asks_after_the_counts() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.TIMEOUT, solver_seconds=10.0005)

    lines = render_stop(stopped_with(Stop(kind=StopKind.NO_FORK), miss)).splitlines()

    assert lines[2] == "solver seconds: 0.000 sat, 0.000 unsat, 0.000 unknown, 10.001 timeout"
