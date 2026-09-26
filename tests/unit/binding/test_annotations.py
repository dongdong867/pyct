import pytest

from pyct.binding.annotations import Check, Items, check_of, contradictions
from pyct.run.target import Target


def test_contradictions_names_the_parameter_the_type_and_the_value() -> None:
    assert contradictions({"s": str}, {"s": 5}) == ["s must be a str, got 5"]


def test_contradictions_spells_the_value_as_json() -> None:
    assert contradictions({"n": int}, {"n": "5"}) == ['n must be an int, got "5"']


def test_contradictions_says_an_before_int() -> None:
    assert contradictions({"n": int}, {"n": 1.5}) == ["n must be an int, got 1.5"]


def test_contradictions_follows_python_on_numbers() -> None:
    # bool is an int to Python, and an int is accepted where a float is asked for
    assert contradictions({"n": int, "x": float, "y": float}, {"n": True, "x": 3, "y": False}) == []


def test_contradictions_refuses_an_int_for_a_bool() -> None:
    assert contradictions({"b": bool}, {"b": 1}) == ["b must be a bool, got 1"]


def test_contradictions_refuses_none_for_every_plain_type() -> None:
    hints = {"s": str, "n": int, "x": float, "b": bool}
    assert contradictions(hints, dict.fromkeys(hints)) == [
        "s must be a str, got null",
        "n must be an int, got null",
        "x must be a float, got null",
        "b must be a bool, got null",
    ]


def test_contradictions_keeps_the_signature_order() -> None:
    assert contradictions({"name": str, "age": int}, {"age": "x", "name": 5}) == [
        "name must be a str, got 5",
        'age must be an int, got "x"',
    ]


def test_contradictions_ignores_a_parameter_the_seed_does_not_name() -> None:
    assert contradictions({"s": str}, {}) == []


def test_contradictions_accepts_a_matching_seed() -> None:
    assert contradictions({"s": str, "n": int}, {"s": "abc", "n": 1}) == []


@pytest.mark.parametrize(
    ("annotation", "check"),
    [
        pytest.param(str, str, id="str"),
        pytest.param(bool, bool, id="bool"),
        pytest.param(list, Items(list, None), id="bare list"),
        pytest.param(dict, Items(dict, None), id="bare dict"),
        pytest.param(list[int], Items(list, int), id="list of int"),
        pytest.param(dict[str, float], Items(dict, float), id="dict of float"),
        pytest.param(
            list[dict[str, list[bool]]], Items(list, Items(dict, Items(list, bool))), id="deep"
        ),
    ],
)
def test_check_of_reads_a_plain_list_or_dict_annotation(annotation: object, check: Check) -> None:
    assert check_of(annotation) == check


@pytest.mark.parametrize(
    "annotation",
    [
        pytest.param(tuple[int, int], id="tuple"),
        pytest.param(dict[int, str], id="int keys"),
        pytest.param(list[int] | None, id="union"),
        pytest.param(list[int | None], id="union inside"),
        pytest.param(dict[str, Target], id="class inside"),
        pytest.param(Target, id="class"),
        # Python builds this alias without a word; only a type checker refuses it
        pytest.param(list[int, str], id="two items"),  # pyrefly: ignore[bad-specialization]
    ],
)
def test_check_of_asks_nothing_of_any_other_annotation(annotation: object) -> None:
    assert check_of(annotation) is None


def test_contradictions_names_an_item_by_its_access_as_python_writes_it() -> None:
    checks: dict[str, Check] = {"xs": Items(list, int), "cfg": Items(dict, Items(list, str))}

    assert contradictions(checks, {"xs": [1, True, "2"], "cfg": {"a": ["b", 3], "it's": [4]}}) == [
        'xs[2] must be an int, got "2"',
        "cfg['a'][1] must be a str, got 3",
        'cfg["it\'s"][0] must be a str, got 4',
    ]


def test_contradictions_refuses_a_container_of_the_wrong_kind() -> None:
    checks: dict[str, Check] = {"items": Items(list, None), "cfg": Items(dict, int)}

    assert contradictions(checks, {"items": {"a": 1}, "cfg": [1]}) == [
        'items must be a list, got {"a": 1}',
        "cfg must be a dict, got [1]",
    ]


def test_contradictions_checks_the_kind_alone_for_a_bare_list() -> None:
    assert contradictions({"items": Items(list, None)}, {"items": [1, "a", None]}) == []


def test_contradictions_gives_an_item_the_allowances_a_parameter_has() -> None:
    checks: dict[str, Check] = {"xs": Items(list, float)}

    assert contradictions(checks, {"xs": [1, True, 2.5]}) == []
