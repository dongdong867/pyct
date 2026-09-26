"""The harness the compare tool's acceptance tests share: a checker past its timeout."""

import os
import subprocess
import time

import pytest

from tests.compare_coverage.acceptance.checker import ONE_CHECK, run_checker
from tests.compare_coverage.conftest import StubCheckout


def running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_checker_past_its_timeout_is_interrupted_and_stops_its_side(
    stub_checkout: StubCheckout,
) -> None:
    stub_checkout.script({ONE_CHECK: {"sleep": 60}})

    with pytest.raises(subprocess.TimeoutExpired):
        run_checker("--legacy", str(stub_checkout.path), "--target", ONE_CHECK, timeout=5)

    # the side leads a session of its own, so only the checker's Ctrl-C path can stop it
    side = stub_checkout.calls()[-1]["pid"]
    deadline = time.monotonic() + 5
    while running(side) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not running(side)
