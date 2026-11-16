"""An instance's field is read only as the instance stores it, in its ``__dict__`` or a slot, and
only when its value is plain data; no hook of the class, its metaclass, a key or the value runs to
tell. Each hook writes a file of its own name, so a test that finds no file saw none run."""

import datetime
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pyct.binding.stored import (
    ABSENT,
    AN_OBJECT,
    BORROWED,
    BY_CODE,
    FieldUnreadError,
    plain_data,
    read_field,
)
from pyct.core.foundation.branch import SinkItem
from pyct.core.lists.lists import ConcolicList
from pyct.core.strs.strs import ConcolicStr
from tests.unit.binding import stored_classes as tricky


@pytest.fixture(autouse=True)
def hooks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """The folder each hook writes its file in; the test fails when any is there."""
    monkeypatch.setenv("PYCT_TEST_HOOKS", str(tmp_path))
    yield tmp_path
    assert sorted(path.name for path in tmp_path.iterdir()) == []


def refused(owner: object, field: str = "code") -> str:
    with pytest.raises(FieldUnreadError) as raised:
        read_field(owner, "order", field)
    return raised.value.reason


def test_a_field_the_instance_stores_is_read_as_stored() -> None:
    assert read_field(tricky.Plain("1"), "order", "code") == "1"


def test_a_field_stored_over_a_method_s_name_is_the_instance_s() -> None:
    plain = tricky.Plain("1")
    plain.cancel = "2"  # pyrefly: ignore[bad-assignment]

    assert read_field(plain, "order", "cancel") == "2"


def test_a_slot_is_read_and_an_empty_one_holds_no_field() -> None:
    assert read_field(tricky.Slots("1"), "order", "code") == "1"
    assert refused(tricky.Slots()) == f"it cannot read order.code: {ABSENT}"


@pytest.mark.parametrize(
    "built",
    [
        lambda: tricky.Prop("1"),
        lambda: tricky.Gated("1"),
        lambda: tricky.PropOverSlot("1"),
        lambda: tricky.DictProp("1"),
        tricky.DataDesc,
    ],
    ids=["property", "own __getattribute__", "property over a slot", "__dict__ property", "data"],
)
def test_a_name_the_class_answers_with_code_is_not_read(built: Callable[[], object]) -> None:
    assert refused(built()) == f"it cannot read order.code: {BY_CODE}"


@pytest.mark.parametrize(
    "built", [tricky.BorrowedSlot, tricky.BorrowedDict], ids=["slot", "__dict__"]
)
def test_a_field_behind_another_class_s_descriptor_is_not_read(built: Callable[[], object]) -> None:
    assert refused(built()) == f"it cannot read order.code: {BORROWED}"


def test_a_c_type_s_own_getter_is_not_read() -> None:
    assert refused(datetime.date(2026, 1, 1), "year") == f"it cannot read order.year: {BY_CODE}"


@pytest.mark.parametrize(
    ("built", "field"),
    [
        (lambda: tricky.Answering("1"), "code"),
        (tricky.ClassOnly, "code"),
        (lambda: tricky.Plain("1"), "cost"),
        (lambda: tricky.Plain("1"), "cancel"),
    ],
    ids=["__getattr__", "class attribute", "missing", "method"],
)
def test_a_name_the_instance_does_not_store_is_no_field(
    built: Callable[[], object], field: str
) -> None:
    assert refused(built(), field) == f"it cannot read order.{field}: {ABSENT}"


def test_a_metaclass_s_hooks_do_not_run() -> None:
    assert read_field(tricky.WithMeta("1"), "order", "code") == "1"


def test_a_class_property_does_not_run() -> None:
    assert read_field(tricky.ClassProp("1"), "order", "code") == "1"


def test_a_key_of_the_same_hash_is_not_compared(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = tricky.Plain("1")
    vars(owner)[tricky.SameHash()] = "2"  # pyrefly: ignore[unsupported-operation]
    monkeypatch.setattr(tricky.SameHash, "armed", True)

    assert read_field(owner, "order", "code") == "1"


@pytest.mark.parametrize(
    "made",
    [
        lambda: tricky.Code("1"),
        lambda: tricky.Level.LOW,
        lambda: tricky.Tagged(["1"]),
        lambda: tricky.Plain("1"),
        lambda: ["1", [tricky.Plain("1")]],
        lambda: {"k": (1, tricky.Code("1"))},
        lambda: {tricky.Code("k"): 1},
        lambda: tricky.MetaValue(),
        lambda: [tricky.MetaValue],
        lambda: range(3),
    ],
    ids=[
        "str subclass",
        "IntEnum",
        "list subclass",
        "object",
        "object in a list",
        "subclass in a tuple",
        "subclass key",
        "metaclass instance",
        "class",
        "range",
    ],
)
def test_a_field_whose_value_is_not_plain_data_is_not_read(made: Callable[[], object]) -> None:
    assert refused(tricky.Plain(made())) == f"it cannot read order.code: {AN_OBJECT}"


def test_plain_data_at_any_depth_is_read() -> None:
    value = {"a": [1, 2.5, (True, None)], "b": {"c": "d"}}
    cycle: list[object] = [1]
    cycle.append(cycle)

    assert read_field(tricky.Plain(value), "order", "code") is value
    assert plain_data(cycle)


def test_values_pyct_tracks_are_plain_data() -> None:
    sink: list[SinkItem] = []
    code = ConcolicStr.made("1", expression="s", sink=sink)
    tags = ConcolicList.made([code], "t", sink)  # pyrefly: ignore[bad-argument-type]

    assert read_field(tricky.Plain(code), "order", "code") is code
    assert plain_data({"tags": tags})
    assert sink == []
