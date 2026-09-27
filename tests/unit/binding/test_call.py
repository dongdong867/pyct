import inspect

from pyct.binding.call import call_arguments, positional_only


def takes_two_by_position(a: int, b: int = 2, /, c: int = 3, *, d: int = 4) -> None:
    pass


def two_defaults(a: int = 1, b: int = 2, /) -> None:
    pass


POSITIONAL = positional_only(inspect.signature(takes_two_by_position))


def test_a_positional_only_parameter_goes_by_position_and_the_rest_by_name() -> None:
    assert call_arguments(POSITIONAL, {"a": 1, "c": 5, "d": 6}) == ((1,), {"c": 5, "d": 6})


def test_positional_only_parameters_go_in_signature_order_whatever_the_seed_order() -> None:
    assert call_arguments(POSITIONAL, {"b": 7, "a": 1}) == ((1, 7), {})


def test_a_skipped_position_before_a_given_one_takes_its_default() -> None:
    positional = positional_only(inspect.signature(two_defaults))

    assert call_arguments(positional, {"b": 5}) == ((1, 5), {})


def test_a_position_after_the_last_given_one_is_left_to_its_default() -> None:
    assert call_arguments(positional_only(inspect.signature(two_defaults)), {}) == ((), {})


def test_a_missing_position_with_no_default_leaves_the_rest_by_name() -> None:
    # passing b by name lets Python's own binding say that a is missing
    assert call_arguments(POSITIONAL, {"b": 7}) == ((), {"b": 7})


def test_a_function_with_no_positional_only_parameter_takes_every_value_by_name() -> None:
    def plain(x: int, y: int) -> None:
        pass

    assert call_arguments(positional_only(inspect.signature(plain)), {"y": 2, "x": 1}) == (
        (),
        {"y": 2, "x": 1},
    )


def test_positional_only_names_the_parameters_before_the_slash() -> None:
    assert [parameter.name for parameter in POSITIONAL] == ["a", "b"]
