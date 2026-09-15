from pyct.config.plateau import Plateau


def test_a_plateau_with_nothing_set_is_no_plateau_stop() -> None:
    assert Plateau().inputs is None
