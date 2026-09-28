"""A tracked dict's views read as Python's view types and refuse a pickle or a copy as Python's
views do, each recording nothing (read-a-dict-view-s-type-as-python-s,
refuse-a-tracked-dict-view-s-pickle-as-python-does)."""

import copy
import pickle
from collections.abc import Callable, ItemsView, KeysView, ValuesView

import pytest

from pyct.core.bound import type_
from pyct.core.values import raised_by_target
from tests.unit.core.test_dicts import tracked

VIEWS = [("keys", KeysView), ("values", ValuesView), ("items", ItemsView)]
VIEW_IDS = [name for name, _ in VIEWS]


@pytest.mark.parametrize(("name", "registered"), VIEWS, ids=VIEW_IDS)
def test_a_view_reads_as_python_s_view_type(name: str, registered: type) -> None:
    config, sink = tracked({"a": 1})
    view = getattr(config, name)()
    python = type(getattr({}, name)())

    assert type_(view) is python and view.__class__ is python
    assert isinstance(view, python) and isinstance(view, registered)
    # pyct tells its view apart by the real type, which stays its own
    assert type(view) is not python and isinstance(view, type(view))
    assert sink == []


def test_a_plain_view_s_type_is_python_s_own() -> None:
    assert type_({}.keys()) is type({}.keys())


@pytest.mark.parametrize(("name", "_registered"), VIEWS, ids=VIEW_IDS)
@pytest.mark.parametrize("kind", [dict, type({}.keys()), 5])
def test_assigning_a_view_s_class_raises_what_python_raises(
    name: str, _registered: type, kind: object
) -> None:
    config, sink = tracked({"a": 1})
    view = getattr(config, name)()
    python = getattr({}, name)()

    for assign in (setattr, object.__setattr__):
        with pytest.raises(TypeError) as plain:
            assign(python, "__class__", kind)
        with pytest.raises(TypeError) as raised:
            assign(view, "__class__", kind)
        assert str(raised.value) == str(plain.value)
        assert raised_by_target(raised.value)
    assert sink == []


def _refusals() -> list[object]:
    """Each way a target asks for a view's pickle or copy, named for its test."""
    protocols = range(pickle.HIGHEST_PROTOCOL + 1)
    pickles = [
        pytest.param(
            lambda value, protocol=protocol: pickle.dumps(value, protocol), id=f"dumps-{protocol}"
        )
        for protocol in protocols
    ]
    reductions = [
        pytest.param(
            lambda value, protocol=protocol: value.__reduce_ex__(protocol),
            id=f"reduce-ex-{protocol}",
        )
        for protocol in protocols
    ]
    return [
        *pickles,
        *reductions,
        pytest.param(lambda value: value.__reduce__(), id="reduce"),
        pytest.param(copy.copy, id="copy"),
        pytest.param(copy.deepcopy, id="deepcopy"),
    ]


@pytest.mark.parametrize(("name", "_registered"), VIEWS, ids=VIEW_IDS)
@pytest.mark.parametrize("refusal", _refusals())
def test_a_view_refuses_a_pickle_and_a_copy_as_python_s_does(
    name: str, _registered: type, refusal: Callable[[object], object]
) -> None:
    config, sink = tracked({"a": 1})
    with pytest.raises(Exception) as plain:
        refusal(getattr({"a": 1}, name)())
    with pytest.raises(Exception) as raised:
        refusal(getattr(config, name)())

    assert type(raised.value) is type(plain.value)
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    # nothing is written and no answer leaves the dict, so nothing is recorded
    assert sink == []
