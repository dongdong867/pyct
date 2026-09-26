import signal
import time

import pytest

from pyct.execution.deadline import DeadlineError, alarm, deadline
from tests.unit.deadline_fires import DEADLINE_FIRES


@DEADLINE_FIRES
def test_deadline_stops_a_loop_that_never_ends() -> None:
    with pytest.raises(DeadlineError), deadline(time.monotonic() + 0.05):
        while True:
            pass


@DEADLINE_FIRES
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

    # no timer armed: zero seconds to the next fire, zero interval
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_an_alarm_acts_at_the_instant_without_raising() -> None:
    acted: list[float] = []

    with alarm(time.monotonic() + 0.05, lambda *_: acted.append(time.monotonic())):
        # time.sleep resumes after a handler that does not raise, so it sleeps its full time
        time.sleep(0.2)

    assert len(acted) == 1


def test_an_alarm_restores_the_previous_handler_and_cancels_its_timer() -> None:
    before = signal.getsignal(signal.SIGALRM)

    with alarm(time.monotonic() + 10, lambda *_: None):
        pass

    assert signal.getsignal(signal.SIGALRM) is before
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_no_alarm_installs_nothing() -> None:
    before = signal.getsignal(signal.SIGALRM)

    with alarm(None, lambda *_: None):
        inside = signal.getsignal(signal.SIGALRM)

    assert inside is before
