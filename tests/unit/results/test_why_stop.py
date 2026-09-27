"""The analysis's stop is its own: it reads the clock where its work grows, and touches no signal,
thread or handler, so nothing that lands on the process, a Ctrl-C say, meets a stop of its."""

import dis
import itertools
import signal
import textwrap
import threading
import time
import tracemalloc
import types
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Site
from pyct.results import blocks, why
from pyct.results.graphs import OutOfTimeError, Pace
from pyct.results.way import Flow
from pyct.results.why import Reason, Run, Walked, explain

SOURCE = """\
def f(x):
    y = int("x")
    if x > 0:
        return y
    return 0
"""


def module(tmp_path: Path, source: str = SOURCE, name: str = "m.py") -> str:
    file = tmp_path / name
    file.write_text(textwrap.dedent(source))
    return str(file)


def test_a_stop_touches_no_signal_and_starts_no_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    handler = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()
    seen: list[tuple[object, int]] = []
    marked = Flow.marked

    def looking(flow: Flow, *args: object) -> frozenset[int]:
        seen.append((signal.getsignal(signal.SIGALRM), threading.active_count()))
        return marked(flow, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(Flow, "marked", looking)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]

    explain(
        file, frozenset({3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=time.monotonic() + 60)
    )

    assert seen, "the analysis marked nothing"
    assert set(seen) == {(handler, threads)}
    assert signal.getsignal(signal.SIGALRM) is handler
    assert threading.active_count() == threads


def test_a_ctrl_c_inside_the_analysis_reaches_the_caller_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)

    def interrupted(flow: Flow, *args: object) -> frozenset[int]:
        raise KeyboardInterrupt

    monkeypatch.setattr(Flow, "marked", interrupted)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]

    with pytest.raises(KeyboardInterrupt) as raised:
        run = Run(walked, {}, stop_at=time.monotonic() + 60)
        explain(file, frozenset({3, 4, 5}), frozenset({2}), run)

    # the Ctrl-C itself, with no stop of the analysis chained to it
    assert raised.value.__context__ is None or not isinstance(
        raised.value.__context__, OutOfTimeError
    )


def test_a_step_that_runs_long_stops_at_its_next_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    marked = Flow.marked

    def slow(flow: Flow, *args: object) -> frozenset[int]:
        # a step made of many small ones, each a tenth of a millisecond, with the pace between
        # them: far slower than a real step, which is a node, a line or an input
        for _ in range(100_000):
            time.sleep(0.0001)
            flow.pace.step()
        return marked(flow, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(Flow, "marked", slow)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    stop_at = time.monotonic() + 0.2

    entries = explain(file, frozenset({3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=stop_at))
    ended = time.monotonic()

    assert [(entry.lines, entry.reason) for entry in entries] == [
        ((3, 4, 5), Reason.NOT_WORKED_OUT)
    ]
    assert ended - stop_at < 0.1, ended - stop_at


def _joined(
    tests: int, _file: str = ""
) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    ifs = "".join(f"    if v == {k} or v == {-k - 1}:\n        y += {k}\n" for k in range(tests))
    source = f"def f(x):\n    v = x ^ 0\n    y = 0\n{ifs}    return y\n"
    bodies = frozenset(range(5, 5 + 2 * tests, 2))
    covered = frozenset({2, 3, 4 + 2 * tests}) | frozenset(range(4, 4 + 2 * tests, 2))
    return source, bodies, covered, [Walked(forks=(), failed=False, lines=covered)]


def _tries(
    blocks: int, _file: str = ""
) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    body = "".join(
        f"    try:\n        y += int('{k}')\n    except ValueError:\n        y = {k}\n"
        for k in range(blocks)
    )
    source = f"def f(x):\n    y = 0\n{body}    return y\n"
    handlers = frozenset(line for k in range(blocks) for line in (5 + 4 * k, 6 + 4 * k))
    covered = frozenset(range(2, 3 + 4 * blocks + 1)) - handlers
    return source, handlers, covered, [Walked(forks=(), failed=False, lines=covered)]


def _paths(tests: int, _file: str = "") -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    ifs = "".join(f"    if x == {k}:\n        y += {k}\n" for k in range(tests))
    after = "".join(f"    y += {k}\n" for k in range(20))
    source = f"def gen(x):\n    y = 0\n{ifs}    yield y\n{after}    yield y\n"
    yield_line = 3 + 2 * tests
    tested = frozenset(range(3, yield_line, 2))
    walked = [
        Walked(forks=(), failed=False, lines=frozenset({2, yield_line, 4 + 2 * k}) | tested)
        for k in range(tests)
    ]
    covered = frozenset().union(*(each.lines for each in walked))
    return source, frozenset(range(yield_line + 1, yield_line + 22)), covered, walked


def _raising(lines: int, file: str) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    body = "".join(f"    y += 10 // (x + {k})\n" for k in range(lines))
    source = f"def f(x):\n    y = 0\n{body}    if y > 3:\n        y = 1\n    return y\n"
    covered = frozenset(range(2, 4 + lines)) | {5 + lines}
    # each division records its fork before it may raise, and the test after them its own
    forks = tuple(
        Branch(["!=", ["+", "x", k], 0], True, Site(file, 3 + k, 9), raising=True)
        for k in range(lines)
    ) + (Branch([">", "y", 3], False, Site(file, 3 + lines, 7)),)
    return source, frozenset({4 + lines}), covered, [Walked(forks, False, covered)]


def _ifs(tests: int, _file: str) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    ifs = "".join(f"    if x == {k}:\n        y += {k}\n" for k in range(tests))
    source = f"def f(x):\n    y = 0\n{ifs}    return y\n"
    covered = frozenset({2, 3 + 2 * tests}) | frozenset(range(3, 3 + 2 * tests, 2))
    bodies = frozenset(range(4, 4 + 2 * tests, 2))
    return source, bodies, covered, [Walked((), False, covered)]


def _if_else_in_a_try(
    lines: int, _file: str
) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    yes = "".join(f"            y += {k}\n" for k in range(lines))
    no = "".join(f"            y -= {k}\n" for k in range(lines))
    source = (
        f"def f(x):\n    y = 0\n    try:\n        if x:\n{yes}        else:\n{no}"
        "    except ValueError:\n        y = -1\n    return y\n"
    )
    handler = frozenset({6 + 2 * lines, 7 + 2 * lines})
    covered = frozenset(range(2, 6 + 2 * lines)) - {5 + lines} | {8 + 2 * lines}
    return source, handler, covered, [Walked((), False, covered)]


def _one_long_and(
    terms: int, _file: str
) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    test = " and ".join(f"x != {k}" for k in range(terms))
    source = f"def f(x):\n    y = 0\n    if {test}:\n        y = 1\n    return y\n"
    covered = frozenset({2, 3, 5})
    return source, frozenset({4}), covered, [Walked((), False, covered)]


# the large shapes the reviews met: joined plain conditions, many try blocks, a generator with a
# path per input, many operations that may raise, many jumps, a long if/else inside a try, and
# one line of many tests
SHAPES = {
    "joined": (_joined, 3000),
    "tries": (_tries, 2000),
    "paths": (_paths, 1600),
    "raising": (_raising, 8000),
    "jumps": (_ifs, 20000),
    "if_else_in_a_try": (_if_else_in_a_try, 8000),
    "one_long_and": (_one_long_and, 4000),
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_the_clock_is_read_often_through_each_large_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    build, size = SHAPES[shape]
    file = str(tmp_path / f"{shape}.py")
    source, uncovered, covered, walked = build(size, file)
    Path(file).write_text(source)
    reads: list[float] = []

    def clock() -> float:
        reads.append(time.monotonic())
        return reads[-1]

    monkeypatch.setattr(why, "clock", clock)
    started = time.monotonic()

    entries = explain(file, uncovered, covered, Run(walked, {}, stop_at=started + 1.5))
    marks = [started, *reads, time.monotonic()]

    assert sorted(line for entry in entries for line in entry.lines) == sorted(uncovered)
    # a stop lands at the first read after it, so the longest stretch between two reads, or
    # after the last, is the most the analysis runs past its stop; the grace is 0.5 s
    longest = max(later - earlier for earlier, later in itertools.pairwise(marks))
    assert longest < 0.15, longest


def test_a_stop_lands_while_the_instructions_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    source, *_ = _tries(200)
    code = compile(source, "m.py", "exec").co_consts[0]
    total = len(list(dis.get_instructions(code)))
    read: list[object] = []
    op = blocks._op

    def reading(instruction: dis.Instruction) -> blocks.Op:
        read.append(instruction)
        return op(instruction)

    monkeypatch.setattr(blocks, "_op", reading)

    # reading a large function's instructions is the first work that grows, so it checks too
    with pytest.raises(OutOfTimeError):
        Flow(code, frozenset(), late=lambda _ahead: True)
    assert len(read) < total, total


def _peak(tmp_path: Path, tests: int) -> int:
    source, uncovered, covered, walked = _joined(tests)
    file = module(tmp_path, source, f"joined{tests}.py")
    tracemalloc.start()
    try:
        explain(file, uncovered, covered, Run(walked, {}))
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_the_memory_the_analysis_keeps_grows_with_the_function_not_its_square(
    tmp_path: Path,
) -> None:
    # what one line's search found is kept for that line alone: kept for every line, it grows
    # as lines times nodes, and the collector's pauses over it are stretches no step can check
    small, large = _peak(tmp_path, 100), _peak(tmp_path, 200)

    assert large < 3 * small, (small, large)


def _many_jumps(tests: int) -> types.CodeType:
    source, *_ = _ifs(tests, "")
    code = compile(source, "m.py", "exec").co_consts[0]
    assert isinstance(code, types.CodeType)
    return code


def test_a_function_whose_labels_cannot_be_read_before_the_stop_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[object] = []
    op = blocks._op
    monkeypatch.setattr(
        blocks, "_op", lambda instruction: read.append(instruction) or op(instruction)
    )
    code = _many_jumps(20000)
    asked: list[float] = []

    def late(ahead: float) -> bool:
        asked.append(ahead)
        return ahead > 0.1

    # dis finds every jump's label before it hands out the first instruction, a pass no step
    # can break into, so the stop is asked ahead of it
    with pytest.raises(OutOfTimeError):
        Flow(code, frozenset(), late=late)
    assert read == []
    assert asked[0] > 0.1


def test_the_label_pass_is_asked_for_no_less_than_it_takes() -> None:
    code = _many_jumps(10000)
    asked: list[float] = []

    def late(ahead: float) -> bool:
        asked.append(ahead)
        return False

    blocks.blocks_of_code(code, frozenset(), Pace(late))
    started = time.perf_counter()
    next(iter(dis.get_instructions(code)))
    took = time.perf_counter() - started

    assert asked[0] >= took, (asked[0], took)
