from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau


def test_limits_with_nothing_set_bound_a_run_neither_way() -> None:
    assert Limits().budget == Budget()
    assert Limits().plateau == Plateau()


def test_limits_given_a_plateau_leave_the_budget_unset() -> None:
    assert Limits(plateau=Plateau(inputs=2)).budget == Budget()
