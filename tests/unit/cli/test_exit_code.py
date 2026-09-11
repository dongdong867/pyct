from pyct.cli import _exit_code
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import InputRecord


def record_of(failure: Failure | None) -> InputRecord:
    return InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)


def test_exit_code_is_one_when_pyct_itself_broke() -> None:
    record = record_of(Failure(kind=FailureKind.PYCT_BUG, detail="RuntimeError: boom"))

    assert _exit_code(record) == 1


def test_exit_code_is_zero_when_the_target_raised() -> None:
    record = record_of(Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small"))

    assert _exit_code(record) == 0


def test_exit_code_is_zero_when_the_call_returned() -> None:
    assert _exit_code(record_of(None)) == 0
