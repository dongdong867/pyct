"""A pickle of a tracked value holds its plain value, and writing it is a downgrade.

The rule is pickle-holds-the-plain-value: a pickle can load in another process or a later
input, where the condition does not apply. A copy is apart from it and stays the value itself.
"""

import copy
import pickle
from collections.abc import Callable
from multiprocessing.reduction import ForkingPickler
from unittest.mock import ANY

import pytest

from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# each concolic type built on a sink: how to make one, and the plain value Python's own holds
TRACKED: dict[str, tuple[Callable[[list[SinkItem]], object], object]] = {
    "a tracked int": (lambda sink: ConcolicInt(3, expression="n", sink=sink), 3),
    "a compare's answer": (lambda sink: ConcolicInt(3, expression="n", sink=sink) > 0, True),
    "a tracked str": (lambda sink: ConcolicStr("ab", expression="s", sink=sink), "ab"),
    "a tracked float": (lambda sink: ConcolicFloat(2.5, expression="x", sink=sink), 2.5),
}
PROTOCOLS = range(pickle.HIGHEST_PROTOCOL + 1)


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_a_round_trip_loads_the_plain_value_at_every_protocol(
    make: Callable[[list[SinkItem]], object], plain: object, protocol: int
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    loaded = pickle.loads(pickle.dumps(value, protocol))

    # Python's own type and value, carrying nothing: an int, a bool, a str and a float
    assert type(loaded) is type(plain)
    assert loaded == plain
    assert sink == [Downgrade(name="__reduce_ex__", site=ANY)]


@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_multiprocessing_pickles_the_plain_value(
    make: Callable[[list[SinkItem]], object], plain: object
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    # the pickler multiprocessing hands a value to another process with
    loaded = pickle.loads(ForkingPickler.dumps(value))

    assert type(loaded) is type(plain)
    assert loaded == plain
    assert sink == [Downgrade(name="__reduce_ex__", site=ANY)]


def test_each_tracked_value_in_a_container_is_one_downgrade() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)
    s = ConcolicStr("ab", expression="s", sink=sink)

    # n and s each appear twice, and pickle writes a value once and refers back to it, so
    # three values are written: n, s and the compare's answer
    loaded = pickle.loads(pickle.dumps({"n": n, "s": s, "k": 1, "all": [n, n > 0, (s,)]}))

    assert loaded == {"n": 3, "s": "ab", "k": 1, "all": [3, True, ("ab",)]}
    assert [type(item) for item in loaded["all"]] == [int, bool, tuple]
    assert sink == [Downgrade(name="__reduce_ex__", site=ANY)] * 3


def test_the_pickled_value_keeps_its_condition() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)

    pickle.dumps(n)
    bigger = n > 10

    assert (n.expression, n.sink) == ("n", sink)
    assert isinstance(bigger, int)
    assert getattr(bigger, "expression", None) == [">", "n", 10]


@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_reduce_takes_the_arguments_pythons_own_takes(
    make: Callable[[list[SinkItem]], object], plain: object
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    # one protocol and none, as on a plain value; a refused call records nothing
    for call in (lambda v: v.__reduce_ex__(), lambda v: v.__reduce__(2)):
        with pytest.raises(TypeError):
            call(plain)
        with pytest.raises(TypeError):
            call(value)
    assert sink == []


@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_reduce_called_by_its_own_name_is_a_downgrade_by_that_name(
    make: Callable[[list[SinkItem]], object], plain: object
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    rebuilt, (held,) = value.__reduce__()

    assert rebuilt is type(plain)
    assert type(held) is type(plain)
    assert held == plain
    assert sink == [Downgrade(name="__reduce__", site=ANY)]


@pytest.mark.parametrize("copied", [copy.copy, copy.deepcopy], ids=["copy", "deepcopy"])
@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_a_copy_is_the_value_itself_and_asks_nothing_of_pickling(
    make: Callable[[list[SinkItem]], object], plain: object, copied: Callable[[object], object]
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    # the copy module asks for __copy__ and __deepcopy__ before it would reduce the value
    held = copied([value])
    assert copied(value) is value
    assert isinstance(held, list)
    assert held[0] is value
    assert sink == []


@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_a_protocol_pickle_refuses_raises_before_anything_is_written(
    make: Callable[[list[SinkItem]], object], plain: object
) -> None:
    sink: list[SinkItem] = []
    value = make(sink)

    with pytest.raises(ValueError) as refused:
        pickle.dumps(plain, protocol=99)
    with pytest.raises(ValueError) as raised:
        pickle.dumps(value, protocol=99)

    assert str(raised.value) == str(refused.value)
    assert sink == []


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize(("make", "plain"), TRACKED.values(), ids=list(TRACKED))
def test_a_tracked_values_pickle_is_other_bytes_that_load_to_the_same_value(
    make: Callable[[list[SinkItem]], object], plain: object, protocol: int
) -> None:
    written = pickle.dumps(make([]), protocol)
    own = pickle.dumps(plain, protocol)

    # the pickler writes an exact int, bool or str by its type and asks a tracked one for
    # __reduce_ex__, so the bytes differ; what they load to does not
    assert written != own
    assert type(pickle.loads(written)) is type(pickle.loads(own))
    assert pickle.loads(written) == pickle.loads(own)
