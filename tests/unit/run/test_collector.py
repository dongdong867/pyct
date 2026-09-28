"""The cyclic collector held off while pyct's process handles an input, and given back."""

import gc

import pytest

from pyct.run.collector import collector_paused


def test_the_collector_is_off_inside_and_on_again_after() -> None:
    assert gc.isenabled()

    with collector_paused():
        assert not gc.isenabled()

    assert gc.isenabled()


def test_a_collector_the_caller_turned_off_stays_off() -> None:
    gc.disable()
    try:
        with collector_paused():
            assert not gc.isenabled()
        assert not gc.isenabled()
    finally:
        gc.enable()


def test_the_collector_is_on_again_after_a_raise() -> None:
    with pytest.raises(ValueError, match="broke"), collector_paused():
        raise ValueError("broke")

    assert gc.isenabled()
