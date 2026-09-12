from pyct.cli import _exit_code
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import InputRecord

BUG = Failure(kind=FailureKind.PYCT_BUG, detail="RuntimeError: boom")
RAISED = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")


def record_of(failure: Failure | None) -> InputRecord:
    return InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)


def test_exit_code_is_one_when_pyct_itself_broke() -> None:
    assert _exit_code((record_of(BUG),)) == 1


def test_exit_code_is_one_when_the_second_input_broke_pyct() -> None:
    # every input is printed, so the bug can be in any of them
    assert _exit_code((record_of(None), record_of(BUG))) == 1


def test_exit_code_is_zero_when_the_target_raised() -> None:
    assert _exit_code((record_of(RAISED), record_of(RAISED))) == 0


def test_exit_code_is_zero_when_the_call_returned() -> None:
    assert _exit_code((record_of(None),)) == 0
