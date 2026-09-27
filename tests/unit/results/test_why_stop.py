"""The analysis's stop is its own: it reads the clock where its work grows, and touches no signal,
thread or handler, so nothing that lands on the process, a Ctrl-C say, meets a stop of its."""

import signal
import textwrap
import threading
import time
from pathlib import Path

import pytest

from pyct.results.graphs import OutOfTimeError
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


def _joined(tests: int) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    ifs = "".join(f"    if v == {k} or v == {-k - 1}:\n        y += {k}\n" for k in range(tests))
    source = f"def f(x):\n    v = x ^ 0\n    y = 0\n{ifs}    return y\n"
    bodies = frozenset(range(5, 5 + 2 * tests, 2))
    covered = frozenset({2, 3, 4 + 2 * tests}) | frozenset(range(4, 4 + 2 * tests, 2))
    return source, bodies, covered, [Walked(forks=(), failed=False, lines=covered)]


def _tries(blocks: int) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
    body = "".join(
        f"    try:\n        y += int('{k}')\n    except ValueError:\n        y = {k}\n"
        for k in range(blocks)
    )
    source = f"def f(x):\n    y = 0\n{body}    return y\n"
    handlers = frozenset(line for k in range(blocks) for line in (5 + 4 * k, 6 + 4 * k))
    covered = frozenset(range(2, 3 + 4 * blocks + 1)) - handlers
    return source, handlers, covered, [Walked(forks=(), failed=False, lines=covered)]


def _paths(tests: int) -> tuple[str, frozenset[int], frozenset[int], list[Walked]]:
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


# the large shapes the reviews met: joined plain conditions, many try blocks, and a generator
# with a path per input; each is slow enough to pass a stop 0.2 s ahead
SHAPES = {"joined": (_joined, 3000), "tries": (_tries, 2000), "paths": (_paths, 1600)}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_the_stop_lands_within_the_grace_on_each_large_shape(tmp_path: Path, shape: str) -> None:
    build, size = SHAPES[shape]
    source, uncovered, covered, walked = build(size)
    file = module(tmp_path, source, f"{shape}.py")
    stop_at = time.monotonic() + 0.2

    entries = explain(file, uncovered, covered, Run(walked, {}, stop_at=stop_at))
    ended = time.monotonic()

    assert sorted(line for entry in entries for line in entry.lines) == sorted(uncovered)
    assert ended - stop_at < 0.1, ended - stop_at
