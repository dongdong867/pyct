from pyct.config.budget import Budget


def test_a_budget_with_nothing_set_is_no_deadline() -> None:
    assert Budget().seconds is None
