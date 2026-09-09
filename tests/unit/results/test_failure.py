from pyct.results.failure import Failure, FailureKind


def test_a_failure_holds_its_kind_and_a_one_line_detail() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")

    assert failure.kind is FailureKind.TARGET_RAISED
    assert failure.detail == "ValueError: too small"


def test_the_kinds_are_the_words_on_the_line() -> None:
    assert [kind.value for kind in FailureKind] == [
        "timeout",
        "target_raised",
        "system_exit",
        "pyct_bug",
    ]
