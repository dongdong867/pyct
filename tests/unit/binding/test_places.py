from pyct.binding.places import step_in


def test_step_in_writes_a_str_key_as_python_writes_it() -> None:
    assert step_in("self", "owner") == "self['owner']"


def test_step_in_writes_an_index_after_a_place_further_in() -> None:
    assert step_in("rows['c']", 0) == "rows['c'][0]"
