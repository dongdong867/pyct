"""Why a line was missed when the run's deadline comes before pyct worked out every cause."""

import itertools
import textwrap
import threading
from pathlib import Path

import pytest

from pyct.results import why as why_module
from pyct.results.why import Reason, Run, Walked, WhyEntry, explain
from pyct.results.why_render import why_json, why_line

SOURCE = """\
def f(x):
    y = int("x")
    if x > 0:
        return y
    return 0


def helper(z):
    return z
"""


def module(tmp_path: Path) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(SOURCE))
    return str(file)


def clock_after(monkeypatch: pytest.MonkeyPatch, reads: int) -> None:
    """A clock that reads before the stop ``reads`` times, then past it for good."""
    ticks = itertools.chain(itertools.repeat(0.0, reads), itertools.repeat(10.0))
    monkeypatch.setattr(why_module, "clock", lambda: next(ticks))


def explained(file: str, stop_at: float | None) -> tuple[WhyEntry, ...]:
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    uncovered = frozenset({1, 3, 4, 5, 8, 9})
    return explain(file, uncovered, frozenset({2}), Run(walked, {}, stop_at=stop_at))


def test_a_run_past_its_stop_puts_every_line_left_under_not_worked_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    clock_after(monkeypatch, 0)

    entries = explained(file, stop_at=5.0)

    assert entries == (WhyEntry(file=file, lines=(1, 3, 4, 5, 8, 9), reason=Reason.NOT_WORKED_OUT),)


def test_the_lines_worked_out_before_the_stop_keep_their_causes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    # enough reads for the first lines, then the stop comes part way through
    clock_after(monkeypatch, 3)

    entries = explained(file, stop_at=5.0)

    reasons = {line: entry.reason for entry in entries for line in entry.lines}
    assert sorted(reasons) == [1, 3, 4, 5, 8, 9]
    assert reasons[1] is Reason.IMPORT
    assert reasons[9] is Reason.NOT_WORKED_OUT
    assert Reason.NOT_WORKED_OUT in reasons.values()


def test_a_run_with_no_stop_works_out_every_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    clock_after(monkeypatch, 0)

    entries = explained(file, stop_at=None)

    assert Reason.NOT_WORKED_OUT not in {entry.reason for entry in entries}


def test_a_stop_inside_one_line_s_work_leaves_that_line_and_the_rest_unworked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "ends.py"
    file.write_text("def ends(x):\n    y = int(x)\n    z = y\n    return z\n")
    # whether inputs ended before line 3 asks every path's marks
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))] * 3
    walked += [Walked(forks=(), failed=False, lines=frozenset({2}))]
    # the clock is read once per line and once per path's marks, and the four inputs are two
    # paths: the stop comes while the second path's marks are worked out
    clock_after(monkeypatch, 2)

    entries = explain(str(file), frozenset({3, 4}), frozenset({2}), Run(walked, {}, stop_at=5.0))

    assert entries == (WhyEntry(file=str(file), lines=(3, 4), reason=Reason.NOT_WORKED_OUT),)


def test_not_worked_out_reads_as_the_deadline_s() -> None:
    entry = WhyEntry("m.py", (4, 5), Reason.NOT_WORKED_OUT)

    assert why_json(entry) == {"file": "m.py", "lines": [4, 5], "reason": "not worked out"}
    assert why_line(entry) == "why 4, 5 in m.py: not worked out before the deadline"


def _joined(tmp_path: Path, tests: int) -> tuple[str, frozenset[int], frozenset[int]]:
    """``tests`` ifs, each on two plain conditions joined by `or`, none taken: the file, the
    lines left (every if's body), and the lines one input covered."""
    ifs = "".join(f"    if v == {k} or v == {-k - 1}:\n        y += {k}\n" for k in range(tests))
    file = tmp_path / f"joined{tests}.py"
    file.write_text(f"def f(x):\n    v = x ^ 0\n    y = 0\n{ifs}    return y\n")
    bodies = frozenset(range(5, 5 + 2 * tests, 2))
    covered = frozenset({2, 3, 4 + 2 * tests}) | frozenset(range(4, 4 + 2 * tests, 2))
    return str(file), bodies, covered


def test_one_line_s_work_on_a_long_function_still_stops_near_the_stop(tmp_path: Path) -> None:
    file, bodies, covered = _joined(tmp_path, 3000)
    walked = [Walked(forks=(), failed=False, lines=covered)]
    stop_at = why_module.clock() + 0.2

    entries = explain(file, bodies, covered, Run(walked, {}, stop_at=stop_at))
    ended = why_module.clock()

    # every line is in one entry however far the analysis got, and it ended near the stop
    assert sorted(line for entry in entries for line in entry.lines) == sorted(bodies)
    assert ended - stop_at < 0.5, ended - stop_at


def _long_generator(tmp_path: Path, tests: int) -> tuple[str, frozenset[int], list[Walked]]:
    """A generator with ``tests`` ifs before its yield and 20 lines after it, one input per if
    body, each left at the yield: the file, the lines left, the inputs."""
    ifs = "".join(f"    if x == {k}:\n        y += {k}\n" for k in range(tests))
    after = "".join(f"    y += {k}\n" for k in range(20))
    file = tmp_path / "long.py"
    file.write_text(f"def gen(x):\n    y = 0\n{ifs}    yield y\n{after}    yield y\n")
    yield_line = 3 + 2 * tests
    tested = frozenset(range(3, yield_line, 2))
    walked = [
        Walked(forks=(), failed=False, lines=frozenset({2, yield_line, 4 + 2 * k}) | tested)
        for k in range(tests)
    ]
    return str(file), frozenset(range(yield_line + 1, yield_line + 22)), walked


def test_off_the_main_thread_the_clock_checks_still_stop_the_analysis(tmp_path: Path) -> None:
    # the stop reads the clock where the analysis steps, so it holds on any thread
    file, uncovered, walked = _long_generator(tmp_path, 1600)
    covered = frozenset().union(*(each.lines for each in walked))
    ended: list[float] = []
    named: list[int] = []
    stop_at = why_module.clock() + 1.5

    def analyse() -> None:
        entries = explain(file, uncovered, covered, Run(walked, {}, stop_at=stop_at))
        ended.append(why_module.clock())
        named.extend(line for entry in entries for line in entry.lines)

    thread = threading.Thread(target=analyse)
    thread.start()
    thread.join(timeout=30)

    # asserted here, where a failure fails the test
    assert ended, "the analysis did not finish"
    assert ended[0] - stop_at < 0.5, ended[0] - stop_at
    assert sorted(named) == sorted(uncovered)
