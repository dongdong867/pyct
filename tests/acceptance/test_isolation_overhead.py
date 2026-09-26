"""The cost of isolation: at most 10 ms per input to a small target whose import leaves no thread.

Measured as the contract says, the same run through the command line with and without
``--in-process``, over at least 50 inputs. Each way runs three times and keeps its fastest,
so a slow moment on the machine does not decide the result.
"""

import time

from tests.acceptance.harness import run_pyct, summary_line

MANY_INPUTS = "targets.isolate.many_inputs::pick"
SEED = '{"x": -1}'
RUNS = 3
MOST_PER_INPUT = 0.010


def fastest(*argv: str) -> tuple[float, int]:
    """The fastest of ``RUNS`` runs, in seconds, and how many inputs each ran."""
    took = []
    inputs = 0
    for _ in range(RUNS):
        started = time.monotonic()
        result = run_pyct(MANY_INPUTS, SEED, *argv)
        took.append(time.monotonic() - started)
        assert result.returncode == 0, result.stderr
        counted = summary_line(result.stdout)["inputs"]
        assert isinstance(counted, int)
        inputs = counted
    return min(took), inputs


def test_isolation_adds_at_most_ten_milliseconds_per_input() -> None:
    isolated, inputs = fastest()
    in_process, same = fastest("--in-process")

    assert inputs == same
    assert inputs >= 50
    assert (isolated - in_process) / inputs < MOST_PER_INPUT, (isolated, in_process, inputs)
