import json
import sys
import threading
from collections import OrderedDict

from pyct.binding.bind import access_name, bind, leaf_name, leaves
from pyct.core.branch import SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr


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


def test_a_str_becomes_a_concolic_str_named_after_its_parameter() -> None:
    sink: list[SinkItem] = []

    args = bind({"s": "text"}, sink)

    bound = args["s"]
    assert isinstance(bound, ConcolicStr)
    assert bound == "text"
    assert bound.expression == "s"
    assert bound.sink is sink


def test_every_other_value_is_a_plain_copy_of_its_own() -> None:
    seed = {"f": 1.5, "n": None, "xs": {1, 2}}

    args = bind(seed, [])

    xs = args["xs"]
    assert args == seed
    assert isinstance(xs, set) and xs is not seed["xs"]
    assert all(type(item) is int for item in xs)


def test_an_empty_seed_binds_to_an_empty_dict() -> None:
    assert bind({}, []) == {}


def test_binding_leaves_the_seed_alone() -> None:
    seed: dict[str, object] = {"x": 3}

    bind(seed, [])

    assert seed == {"x": 3}
    assert not isinstance(seed["x"], ConcolicInt)


def test_leaves_names_the_type_of_every_argument_bind_would_wrap() -> None:
    assert leaves({"x": 3, "flag": True, "name": "a", "f": 1.5}) == {"x": int, "name": str}


def test_leaves_keeps_the_order_the_seed_gave() -> None:
    assert list(leaves({"y": 1, "x": 2})) == ["y", "x"]


def test_an_empty_seed_has_no_leaves() -> None:
    assert leaves({}) == {}


def test_a_value_inside_a_dict_is_named_by_the_access_that_reaches_it() -> None:
    sink: list[SinkItem] = []

    args = bind({"config": {"server": {"port": 80}}}, sink)

    config = args["config"]
    assert isinstance(config, dict)
    port = config["server"]["port"]
    assert isinstance(port, ConcolicInt)
    assert port == 80
    assert port.expression == ["[]", ["[]", "config", "'server'"], "'port'"]
    assert port.sink is sink


def test_a_value_inside_a_list_is_named_by_its_index() -> None:
    args = bind({"items": [1, "a"]}, [])

    items = args["items"]
    assert isinstance(items, list)
    first, second = items
    assert isinstance(first, ConcolicInt)
    assert first.expression == ["[]", "items", 0]
    assert isinstance(second, ConcolicStr)
    assert second.expression == ["[]", "items", 1]


def test_a_key_is_written_as_python_writes_it() -> None:
    args = bind({"d": {"0": 1, "it's": 2}}, [])

    d = args["d"]
    assert isinstance(d, dict)
    assert [value.expression for value in d.values()] == [
        ["[]", "d", "'0'"],
        ["[]", "d", '"it\'s"'],
    ]


def test_an_int_key_names_its_value_by_the_int() -> None:
    args = bind({"by_id": {1: 5}}, [])

    by_id = args["by_id"]
    assert isinstance(by_id, dict)
    assert by_id[1].expression == ["[]", "by_id", 1]


def test_a_value_under_a_key_of_another_type_passes_through() -> None:
    args = bind({"d": {(1, 2): 5, True: 6}}, [])

    d = args["d"]
    assert isinstance(d, dict)
    assert [type(value) for value in d.values()] == [int, int]


def test_keys_nulls_and_bools_inside_stay_plain() -> None:
    args = bind({"d": {"k": None, "b": True, "f": 1.5}}, [])

    d = args["d"]
    assert isinstance(d, dict)
    assert d == {"k": None, "b": True, "f": 1.5}
    assert [type(key) for key in d] == [str, str, str]
    assert d["b"] is True


def test_each_dict_and_list_is_a_copy_of_its_own() -> None:
    seed: dict[str, object] = {"config": {"items": [0]}}

    args = bind(seed, [])

    config = args["config"]
    assert isinstance(config, dict)
    config["items"].append(1)
    config["seen"] = True
    assert seed == {"config": {"items": [0]}}
    assert type(config) is dict
    assert type(config["items"]) is list


def test_a_subclass_of_dict_is_a_copy_of_the_same_type_with_plain_values() -> None:
    seed = {"d": OrderedDict(k=1)}

    args = bind(seed, [])

    d = args["d"]
    assert type(d) is OrderedDict and d is not seed["d"]
    assert d == {"k": 1} and type(d["k"]) is int


def test_a_list_reached_through_a_tuple_is_the_walks_own_copy_there_too() -> None:
    x = [0]
    seed: dict[str, object] = {"a": x, "b": (x,)}

    args = bind(seed, [])

    a, b = args["a"], args["b"]
    assert isinstance(b, tuple) and b[0] is a and a is not x
    assert isinstance(a, list) and isinstance(a[0], ConcolicInt)


def test_a_value_that_cannot_be_copied_reaches_the_target_as_it_came() -> None:
    lock = threading.Lock()

    args = bind({"guard": lock, "x": [0]}, [])

    assert args["guard"] is lock
    assert isinstance(args["x"], list) and isinstance(args["x"][0], ConcolicInt)


def test_leaves_names_each_value_inside_by_its_access_in_seed_order() -> None:
    seed = {"items": [1, "a", True, None], "config": {"k": 2}, "x": 3}

    assert leaves(seed) == {
        json.dumps(["[]", "items", 0]): int,
        json.dumps(["[]", "items", 1]): str,
        json.dumps(["[]", "config", "'k'"]): int,
        "x": int,
    }
    assert list(leaves(seed))[0] == json.dumps(["[]", "items", 0])


def test_leaf_name_is_a_parameters_own_name_or_its_access_as_json() -> None:
    assert leaf_name("x") == "x"
    assert leaf_name(["[]", "items", 0]) == '["[]", "items", 0]'


def test_a_list_that_holds_itself_is_walked_once() -> None:
    xs: list[object] = [0]
    xs.append(xs)

    args = bind({"xs": xs}, [])

    copy = args["xs"]
    assert isinstance(copy, list) and copy is not xs
    assert copy[1] is copy
    assert isinstance(copy[0], ConcolicInt)
    assert leaves({"xs": xs}) == {json.dumps(["[]", "xs", 0]): int}


def test_a_container_reached_twice_is_one_copy_named_by_its_first_path() -> None:
    shared = [0]

    args = bind({"a": shared, "b": shared}, [])

    assert args["a"] is args["b"]
    assert leaves({"a": shared, "b": shared}) == {json.dumps(["[]", "a", 0]): int}


def test_a_seed_nested_past_the_recursion_limit_is_walked() -> None:
    depth = 3 * sys.getrecursionlimit()
    seed: dict[str, object] = {"k": 7}
    for _ in range(depth):
        seed = {"k": seed}

    args = bind({"d": seed}, [])

    node: object = args["d"]
    for _ in range(depth + 1):
        assert isinstance(node, dict)
        node = node["k"]
    assert isinstance(node, ConcolicInt)
    expression = node.expression
    for _ in range(depth + 1):
        assert isinstance(expression, list)
        expression = expression[1]
    assert expression == "d"


def test_a_list_under_a_float_key_is_a_copy_of_its_own_with_plain_values() -> None:
    seed: dict[str, object] = {"table": {1.5: [0], None: {"k": [1]}}}

    args = bind(seed, [])

    table = args["table"]
    assert isinstance(table, dict)
    under_float, under_none = table[1.5], table[None]
    assert under_float == [0] and type(under_float[0]) is int
    under_float.append(99)
    under_none["k"].append(99)
    assert seed == {"table": {1.5: [0], None: {"k": [1]}}}
    # a key no access can name leaves every value under it out of the leaves
    assert leaves(seed) == {}


def test_access_name_reads_only_a_step_the_walk_takes() -> None:
    assert access_name(["[]", "items", 0]) == json.dumps(["[]", "items", 0])
    assert access_name(["+", "x", 1]) is None
    assert access_name("x") is None
    assert access_name([]) is None


def test_a_list_reached_first_under_a_float_key_is_still_named_by_its_key() -> None:
    shared = [0]
    seed: dict[str, object] = {"d": {1.5: shared, "k": shared}}

    args = bind(seed, [])

    d = args["d"]
    assert isinstance(d, dict)
    # one copy for both paths, tracked under the one that names it
    assert d[1.5] is d["k"]
    assert isinstance(d["k"][0], ConcolicInt)
    assert d["k"][0].expression == ["[]", ["[]", "d", "'k'"], 0]
    assert leaves(seed) == {json.dumps(["[]", ["[]", "d", "'k'"], 0]): int}
