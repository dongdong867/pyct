from pyct.binding.bind import bind
from pyct.core.branch import SinkItem
from pyct.core.values import ConcolicInt


def test_an_int_becomes_a_concolic_int_named_after_its_parameter() -> None:
    sink: list[SinkItem] = []

    args = bind({"x": 3}, sink)

    bound = args["x"]
    assert isinstance(bound, ConcolicInt)
    assert bound == 3
    assert bound.expression == "x"
    assert bound.sink is sink


def test_a_bool_is_not_an_int_to_bind() -> None:
    args = bind({"flag": True}, [])

    assert args["flag"] is True


def test_every_other_value_passes_through_untouched() -> None:
    seed = {"s": "text", "f": 1.5, "n": None, "xs": [1, 2]}

    args = bind(seed, [])

    assert args == seed
    assert args["xs"] is seed["xs"]


def test_an_empty_seed_binds_to_an_empty_dict() -> None:
    assert bind({}, []) == {}


def test_binding_leaves_the_seed_alone() -> None:
    seed: dict[str, object] = {"x": 3}

    bind(seed, [])

    assert seed == {"x": 3}
    assert not isinstance(seed["x"], ConcolicInt)
