from pyct.results.failure import Failure, FailureKind


def test_the_kinds_are_the_words_on_the_line() -> None:
    assert [kind.value for kind in FailureKind] == [
        "timeout",
        "target_raised",
        "system_exit",
        "pyct_bug",
    ]


def test_a_pyct_bug_carries_the_whole_traceback() -> None:
    failure = Failure(
        kind=FailureKind.PYCT_BUG, detail="RuntimeError: boom", traceback="Traceback...\nboom\n"
    )

    assert failure.traceback == "Traceback...\nboom\n"


def test_a_failure_has_no_traceback_unless_it_is_given_one() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")

    assert failure.traceback is None
