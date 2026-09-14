from pyct.cli import _exit_code
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import InputRecord, RunResult, Stop, StopKind
from tests.unit.environment import ENVIRONMENT

BUG = Failure(kind=FailureKind.PYCT_BUG, detail="RuntimeError: boom")
RAISED = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")
ATTEMPTED = Stop(kind=StopKind.ONE_ATTEMPT)
COVERAGE = Coverage(covered={"m.py": frozenset()}, total={"m.py": 1})


def record_of(failure: Failure | None) -> InputRecord:
    return InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)


def result_of(*failures: Failure | None, stopped: Stop = ATTEMPTED) -> RunResult:
    records = tuple(record_of(failure) for failure in failures)
    return RunResult(
        entry="m::f",
        records=records,
        coverage=COVERAGE,
        stopped=stopped,
        environment=ENVIRONMENT,
    )


def test_exit_code_is_one_when_pyct_itself_broke() -> None:
    assert _exit_code(result_of(BUG)) == 1


def test_exit_code_is_one_when_the_second_input_broke_pyct() -> None:
    # every input is printed, so the bug can be in any of them
    assert _exit_code(result_of(None, BUG)) == 1


def test_exit_code_is_one_when_the_solver_failed() -> None:
    failed = Stop(kind=StopKind.SOLVER_FAILED, detail="cvc5: boom")

    assert _exit_code(result_of(None, stopped=failed)) == 1


def test_exit_code_is_zero_when_the_target_raised() -> None:
    assert _exit_code(result_of(RAISED, RAISED)) == 0


def test_exit_code_is_zero_when_the_call_returned() -> None:
    assert _exit_code(result_of(None)) == 0
