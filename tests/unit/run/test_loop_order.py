"""The run's loop hands out each fact of a run in the order it happens, and keeps the same
records, misses, untried counts and stop, whatever file holds the loop."""

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord, Miss, Stop, StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from pyct.run.tell import Ask, Tell

# `narrow(x)`: x < 5, then x < 10 under it, which no input can take false there
IMPLIED = "targets.flip.implied_check::narrow"
# `bucket(x)`: x < 100, then x < 10 under it; 5, 50 and 500 take its three paths
BUCKET = "targets.flip.nested_checks::bucket"
# `three_deep(x)`: 30 and 31 take every check's true side, and no flip covers a new line
THREE_DEEP = "targets.flip.flips_gain_nothing::three_deep"

IN_PROCESS = Setup(isolation=Isolation.IN_PROCESS)

type Event = tuple[object, ...]


def heard() -> tuple[Tell, list[Event]]:
    """A Tell that writes down each fact the moment the run hands it out, and the list it
    writes to."""
    events: list[Event] = []

    def report(record: InputRecord, coverage: Coverage) -> None:
        aim = None if record.aim is None else (record.aim.site.line, record.aim.position)
        events.append(("input", record.source.value, record.args["x"], aim))

    def missed(miss: Miss) -> None:
        events.append(("miss", miss.site.line, miss.why.value))

    def asked(ask: Ask) -> None:
        events.append(("ask", ask.number, ask.path, ask.aim.site.line))

    return Tell(report=report, missed=missed, asked=asked), events


def test_the_seeds_then_each_ask_with_what_it_gave() -> None:
    tell, events = heard()

    result = run(load_target(IMPLIED), [{"x": 3}, {"x": 50}], setup=IN_PROCESS, tell=tell)

    assert events == [
        ("input", "seed", 3, None),
        ("input", "seed", 50, None),
        ("ask", 1, 0, 3),
        ("miss", 3, "unsat"),
    ]
    assert result.stopped == Stop(StopKind.NO_FORK)
    assert result.untried == {}
    assert [miss.site.line for miss in result.misses] == [3]


def test_a_solver_input_starts_from_the_path_it_extends() -> None:
    tell, events = heard()

    result = run(load_target(BUCKET), [{"x": 3}, {"x": 50}], setup=IN_PROCESS, tell=tell)

    assert events == [
        ("input", "seed", 3, None),
        ("input", "seed", 50, None),
        ("ask", 1, 0, 2),
        ("input", "solver", 100, (2, 0)),
    ]
    assert result.stopped == Stop(StopKind.NO_FORK)
    firsts = [sorted(lines) for record in result.records for lines in record.first_covered.values()]
    assert firsts == [[2, 3, 4], [5], [6]]


def test_a_plateau_stop_counts_the_fork_it_picked_as_untried() -> None:
    tell, events = heard()
    limits = Limits(plateau=Plateau(inputs=1))

    result = run(load_target(THREE_DEEP), {"x": 30}, limits=limits, setup=IN_PROCESS, tell=tell)

    assert events == [
        ("input", "seed", 30, None),
        ("ask", 1, 0, 8),
        ("input", "solver", 11, (8, 2)),
    ]
    assert result.stopped == Stop(StopKind.NO_GAIN, plateau=1)
    # the fork at line 6 is open still, and the one at line 4 was picked when the plateau held
    assert {(site.site.line, count) for site, count in result.untried.items()} == {(4, 1), (6, 1)}
