import signal
import time

import pytest

from pyct.execution.deadline import DeadlineError, deadline


def test_deadline_stops_a_loop_that_never_ends() -> None:
    with pytest.raises(DeadlineError), deadline(time.monotonic() + 0.05):
        while True:
            pass


def test_deadline_fires_at_once_when_the_instant_has_passed() -> None:
    with pytest.raises(DeadlineError), deadline(time.monotonic() - 1):
        while True:
            pass


def test_no_deadline_installs_nothing() -> None:
    before = signal.getsignal(signal.SIGALRM)

    with deadline(None):
        inside = signal.getsignal(signal.SIGALRM)

    assert inside is before


def test_deadline_restores_the_previous_handler() -> None:
    before = signal.getsignal(signal.SIGALRM)

    with deadline(time.monotonic() + 10):
        pass

    assert signal.getsignal(signal.SIGALRM) is before


def test_deadline_cancels_the_timer_on_the_way_out() -> None:
    with deadline(time.monotonic() + 0.05):
        pass

    # past the instant the timer was set for, and nothing fires
    time.sleep(0.1)
