"""``tests.acceptance.timed`` measures pyct's own run, not the test process that starts it."""

import json
from pathlib import Path

from tests.acceptance.timed import measured

MIB = 1024 * 1024


def test_a_run_s_peak_memory_is_its_own_and_not_the_test_process_s(tmp_path: Path) -> None:
    # a pytest worker late in a run holds hundreds of MiB; this one holds 600 more
    held = bytearray(600 * MIB)
    for page in range(0, len(held), 4096):
        held[page] = 1

    run = measured(
        tmp_path, ["targets.loops.countdown::count_down", "--args", json.dumps({"x": 3})]
    )

    assert run.returncode == 0, run.stderr[-2000:]
    # pyct's interpreter with pyct imported, and the inputs and the cvc5 it waited for
    assert 10 * MIB < run.peak_bytes < 300 * MIB, run.peak_bytes
    assert len(held) == 600 * MIB
