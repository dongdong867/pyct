from pyct.config.budget import Budget


def test_a_budget_holds_its_seconds() -> None:
    budget = Budget(seconds=1.5)

    assert budget.seconds == 1.5


def test_a_budget_with_nothing_set_is_no_deadline() -> None:
    assert Budget().seconds is None
