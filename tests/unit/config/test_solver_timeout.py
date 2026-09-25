from pyct.config.solver_timeout import SolverTimeout


def test_a_solver_timeout_with_nothing_set_is_ten_seconds() -> None:
    assert SolverTimeout().seconds == 10.0
