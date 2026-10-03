"""Which method a call of a range or dict view method through the type runs, and its refusals."""

import types

import pytest

from pyct.core import bound, ranges, type_calls
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.dict_views import ConcolicItems, ConcolicKeys, ConcolicValues
from pyct.core.dicts import ConcolicDict
from pyct.core.ints import ConcolicInt
from pyct.core.ranges import ConcolicRange

EMPTY = (range(0), {}.keys(), {}.values(), {}.items())
CALLED = (types.WrapperDescriptorType, types.MethodDescriptorType)

# a probe whose text is fixed here, so the line of each downgrade is exact. `through` stands for
# the call written `type(r).name(r)`, which interception hands to the router
PROBE = """\
def walked_then_sized(r):
    it = through(range.__iter__)(r)
    return through(range.__len__)(r)

def sized(r):
    return through(range.__len__)(r)
"""


def _probe(name: str, *args: object) -> object:
    namespace: dict[str, object] = {"through": lambda method: bound.CALLED[id(method)]}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace[name]
    assert callable(probe)
    return probe(*args)


def _methods(kind: type) -> list[types.WrapperDescriptorType | types.MethodDescriptorType]:
    return [member for member in vars(kind).values() if isinstance(member, CALLED)]


def _range(n: int) -> tuple[ConcolicRange, list[SinkItem]]:
    sink: list[SinkItem] = []
    built = ranges.ranged(ConcolicInt.made(n, expression="n", sink=sink))
    assert isinstance(built, ConcolicRange)
    return built, sink


def _dict(sink: list[SinkItem]) -> ConcolicDict:
    return ConcolicDict.made({"k": 1}, "d", sink)


def _refusal(call: object) -> str:
    assert callable(call)
    with pytest.raises(TypeError) as raised:
        call()
    return str(raised.value)


def test_each_method_a_type_defines_on_a_value_is_routed() -> None:
    for empty in EMPTY:
        for method in _methods(type(empty)):
            assert method.__name__ in type_calls.NAMES
            assert bound.CALLED[id(method)] is type_calls.ROUTERS[id(method)]
    # a staticmethod never takes a tracked value as its receiver, and object's take any
    assert "__new__" not in type_calls.NAMES
    assert "__format__" not in type_calls.NAMES


def _tracked_and_plain(name: str) -> tuple[object, object]:
    """A tracked range or view, and the plain value of the same type it stands for."""
    if name == "range":
        return _range(3)[0], range(3)
    view = name.removeprefix("dict_")
    return getattr(_dict([]), view)(), getattr({"k": 1}, view)()


@pytest.mark.parametrize("name", ["range", "dict_keys", "dict_values", "dict_items"])
def test_a_keyword_to_each_routed_method_is_refused_as_python_refuses_it(name: str) -> None:
    tracked, plain = _tracked_and_plain(name)
    for method in _methods(type(plain)):
        routed = bound.CALLED[id(method)]
        expected = _refusal(lambda method=method: method(plain, key=0))
        assert _refusal(lambda routed=routed: routed(tracked, key=0)) == expected, method


@pytest.mark.parametrize(
    ("tracked", "empty"),
    [(ConcolicRange, range(0)), (ConcolicKeys, {}.keys())]
    + [(ConcolicValues, {}.values()), (ConcolicItems, {}.items())],
)
def test_python_refuses_one_argument_more_than_the_value_s_own_method_takes(
    tracked: type, empty: object
) -> None:
    # a router hands a count the value's own method does not take to Python's, sure it refuses
    for method in _methods(type(empty)):
        taken = type_calls._taken(getattr(tracked, method.__name__))
        if taken is not None:
            extra = (None,) * (taken + 1)
            _refusal(lambda method=method, extra=extra: method(empty, *extra))


def test_a_tracked_range_runs_its_own_method() -> None:
    r, sink = _range(3)

    assert bound.CALLED[id(range.index)](r, 2) == 2
    assert bound.CALLED[id(range.__contains__)](r, 1)
    # `r.index(2)` is a downgrade, and `1 in r` one fork, tested here
    lost, fork = sink
    assert isinstance(lost, Downgrade) and lost.name == "index"
    assert isinstance(fork, Branch) and fork.expression == ["in", 1, ["range", 0, "n"]]


def test_a_tracked_view_runs_its_own_method() -> None:
    sink: list[SinkItem] = []
    d = _dict(sink)

    assert bound.CALLED[id(type({}.keys()).__len__)](d.keys()) == 1
    assert bound.CALLED[id(type({}.items()).__contains__)](d.items(), ("k", 1))


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    [
        (range.__len__, (1,), {}),
        (range.__contains__, (), {}),
        (range.index, (), {}),
        (range.__contains__, (), {"key": 0}),
    ],
)
def test_a_tracked_range_refuses_what_python_refuses_in_its_words(
    method: object, args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    r, sink = _range(3)
    assert callable(method)
    routed = bound.CALLED[id(method)]

    expected = _refusal(lambda: method(range(3), *args, **kwargs))
    assert _refusal(lambda: routed(r, *args, **kwargs)) == expected
    assert sink == []


def test_another_receiver_gets_python_s_own_method() -> None:
    r, _ = _range(3)
    sink: list[SinkItem] = []
    keys = _dict(sink).keys()
    keys_len = bound.CALLED[id(type({}.keys()).__len__)]

    assert bound.CALLED[id(range.__len__)](range(4)) == 4
    assert keys_len({"a": 1, "b": 2}.keys()) == 2
    assert _refusal(lambda: bound.CALLED[id(range.__len__)](keys)) == _refusal(
        lambda: range.__len__({"k": 1}.keys())  # pyrefly: ignore[bad-argument-type]
    )
    assert _refusal(lambda: keys_len(r)) == _refusal(
        lambda: type({}.keys()).__len__(range(3))  # pyrefly: ignore[bad-argument-type]
    )
    assert _refusal(lambda: bound.CALLED[id(range.__len__)]()) == _refusal(
        lambda: range.__len__()  # pyrefly: ignore[missing-argument]
    )


def test_a_size_after_a_walk_through_the_type_is_the_code_s_own_ask() -> None:
    walked, walked_sink = _range(3)
    sized, sized_sink = _range(3)

    assert _probe("walked_then_sized", walked) == 3
    assert _probe("sized", sized) == 3

    # the code asked the size itself, not Python sizing a walk, as in `r.__iter__(); r.__len__()`
    assert walked_sink == [Downgrade(name="__len__", site=Site(file="<probe>", line=3, col=11))]
    assert sized_sink == [Downgrade(name="__len__", site=Site(file="<probe>", line=6, col=11))]
