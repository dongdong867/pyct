"""A tracked range: a walk records one fork a pass comparing the stop with the element, a
tracked step records its zero and sign forks where the range is built, membership is one
fork, and every other operation is range's own answer and a downgrade."""

import copy
import itertools
import pickle
import random
from collections.abc import Sequence

import pytest

from pyct.core import ranges
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.ranges import ConcolicRange
from pyct.core.values import raised_by_target

# a probe whose text is fixed here, so the line and column of each fork are exact
PROBE = """\
def loop(r):
    out = []
    for i in r:
        out.append(i)
    return out

def listed(r):
    return list(r)

def summed(r):
    return sum(r)

def built(*args):
    return ranged(*args)

def untaught(r):
    return [len(r), r[0], list(reversed(r)), r.count(1), r.index(1), bool(r)]

"""


def _probe(name: str, *args: object) -> object:
    namespace: dict[str, object] = {"ranged": ranges.ranged}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace[name]
    assert callable(probe)
    return probe(*args)


def _int(value: int, sink: list[SinkItem], name: str) -> ConcolicInt:
    return ConcolicInt(value, expression=name, sink=sink)


def _range(*args: object) -> ConcolicRange:
    built = ranges.ranged(*args)
    assert isinstance(built, ConcolicRange)
    return built


def _fork(expression: Expression, taken: bool, line: int = 3, col: int = 13) -> Branch:
    return Branch(expression=expression, taken=taken, site=Site(file="<probe>", line=line, col=col))


def _forms(handed: object) -> list[Expression]:
    """Each element a walk handed out: a tracked int's expression, or the plain int."""
    assert isinstance(handed, list)
    return [item.expression if isinstance(item, ConcolicInt) else item for item in handed]


def test_a_walk_compares_the_stop_with_each_plain_element() -> None:
    sink: list[SinkItem] = []

    handed = _probe("loop", _range(_int(2, sink, "n")))

    # `    for i in r:`: Python places the loop's step at the iterable, column 13
    assert sink == [
        _fork([">", "n", 0], True),
        _fork([">", "n", 1], True),
        _fork([">", "n", 2], False),
    ]
    assert handed == [0, 1] and all(type(i) is int for i in handed)  # pyrefly: ignore


def test_an_element_from_a_tracked_start_adds_no_node_for_zero() -> None:
    sink: list[SinkItem] = []

    handed = _probe("loop", _range(_int(0, sink, "a"), _int(2, sink, "b")))

    assert _forms(handed) == ["a", ["+", "a", 1]]
    assert [fork.expression for fork in sink if isinstance(fork, Branch)] == [
        [">", "b", "a"],
        [">", "b", ["+", "a", 1]],
        [">", "b", ["+", "a", 2]],
    ]


def test_a_negative_step_compares_with_less_than() -> None:
    sink: list[SinkItem] = []

    handed = _probe("loop", _range(_int(2, sink, "n"), 0, -1))

    assert _forms(handed) == ["n", ["+", "n", -1]]
    assert sink == [
        _fork(["<", 0, "n"], True),
        _fork(["<", 0, ["+", "n", -1]], True),
        _fork(["<", 0, ["+", "n", -2]], False),
    ]


def test_a_tracked_step_records_its_forks_where_the_range_is_built() -> None:
    sink: list[SinkItem] = []

    built = _probe("built", 0, 10, _int(4, sink, "k"))
    assert isinstance(built, ConcolicRange)
    handed = _probe("loop", built)

    # the first element depends on no tracked value: it is 0, and its pass records no fork
    assert _forms(handed) == [0, "k", ["*", 2, "k"]]
    assert sink == [
        _fork(["!=", "k", 0], True, line=14, col=11),
        _fork([">", "k", 0], True, line=14, col=11),
        _fork([">", 10, "k"], True),
        _fork([">", 10, ["*", 2, "k"]], True),
        _fork([">", 10, ["*", 3, "k"]], False),
    ]


def test_a_tracked_negative_step_takes_the_other_side_and_walks_down() -> None:
    sink: list[SinkItem] = []

    handed = _probe("loop", _range(_int(3, sink, "a"), 0, _int(-2, sink, "k")))

    assert _forms(handed) == ["a", ["+", "a", "k"]]
    assert [(fork.expression, fork.taken) for fork in sink if isinstance(fork, Branch)] == [
        (["!=", "k", 0], True),
        ([">", "k", 0], False),
        (["<", 0, "a"], True),
        (["<", 0, ["+", "a", "k"]], True),
        (["<", 0, ["+", "a", ["*", 2, "k"]]], False),
    ]


def test_a_zero_step_records_its_fork_and_raises_python_s_value_error() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError) as raised:
        _probe("built", 0, 10, _int(0, sink, "k"))

    with pytest.raises(ValueError) as plain:
        range(0, 10, 0)
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == [_fork(["!=", "k", 0], False, line=14, col=11)]


@pytest.mark.parametrize(
    "args", [("x",), (1, "x"), (1.5,), (1, 2, 3)], ids=["str", "str step", "float", "four"]
)
def test_an_argument_python_refuses_raises_as_python_does_with_no_fork(
    args: tuple[object, ...],
) -> None:
    sink: list[SinkItem] = []
    tracked = (_int(2, sink, "n"), *args)

    with pytest.raises(TypeError) as raised:
        ranges.ranged(*tracked)

    with pytest.raises(TypeError) as plain:
        range(2, *args)  # pyrefly: ignore[no-matching-overload]
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


def test_a_keyword_raises_python_s_type_error() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(TypeError) as raised:
        ranges.ranged(_int(2, sink, "n"), step=1)

    with pytest.raises(TypeError) as plain:
        range(2, step=1)  # pyrefly: ignore[no-matching-overload]
    assert str(raised.value) == str(plain.value)


def test_a_tracked_bool_is_the_int_it_is() -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool(True, expression=[">", "x", 0], sink=sink)

    handed = _probe("loop", _range(flag))

    assert handed == [0]
    assert [fork.expression for fork in sink if isinstance(fork, Branch)] == [
        [">", [">", "x", 0], 0],
        [">", [">", "x", 0], 1],
    ]


def test_any_walk_records_the_forks_at_its_line() -> None:
    sink: list[SinkItem] = []

    assert _probe("summed", _range(_int(3, sink, "n"))) == 3

    assert [(fork.site.line, fork.expression) for fork in sink if isinstance(fork, Branch)] == [
        (11, [">", "n", 0]),
        (11, [">", "n", 1]),
        (11, [">", "n", 2]),
        (11, [">", "n", 3]),
    ]


def test_list_sizes_itself_with_no_downgrade() -> None:
    sink: list[SinkItem] = []

    assert _probe("listed", _range(_int(2, sink, "n"))) == [0, 1]

    # list asks the length only as a guess at the size of the walk it just started
    assert all(isinstance(item, Branch) for item in sink)
    assert len(sink) == 3


def test_membership_in_a_tracked_range_is_one_untested_fork() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(1, sink, "a"), 65536)

    answer = ranges.contains(r, 80)

    assert isinstance(answer, ConcolicBool) and int.__index__(answer) == 1
    assert answer.expression == ["in", 80, ["range", "a", 65536]]
    assert sink == []


def test_membership_writes_the_step_the_target_passed() -> None:
    sink: list[SinkItem] = []
    x = _int(4, sink, "x")

    stepped = ranges.contains(_range(0, _int(10, sink, "n"), 2), x)
    one = ranges.contains(_range(_int(3, sink, "n")), x)

    assert isinstance(stepped, ConcolicBool) and isinstance(one, ConcolicBool)
    assert stepped.expression == ["in", "x", ["range", 0, "n", 2]]
    assert one.expression == ["in", "x", ["range", 0, "n"]]
    assert int.__index__(stepped) == 1 and int.__index__(one) == 0


def test_a_tracked_int_in_a_plain_range_is_one_fork() -> None:
    sink: list[SinkItem] = []
    port = _int(80, sink, "port")

    answer = ranges.within(port, range(1, 65536))
    outside = ranges.not_within(port, range(0, 10, 2))

    assert isinstance(answer, ConcolicBool) and int.__index__(answer) == 1
    assert answer.expression == ["in", "port", ["range", 1, 65536]]
    assert isinstance(outside, ConcolicBool) and int.__index__(outside) == 1
    assert outside.expression == ["not in", "port", ["range", 0, 10, 2]]


def test_not_in_a_tracked_range_is_its_own_head() -> None:
    sink: list[SinkItem] = []

    answer = ranges.not_contains(_range(_int(3, sink, "n")), 5)

    assert isinstance(answer, ConcolicBool) and int.__index__(answer) == 1
    assert answer.expression == ["not in", 5, ["range", 0, "n"]]


def test_an_item_that_is_not_an_int_is_range_s_answer_and_a_downgrade() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(3, sink, "n"))

    assert (1.0 in r) is True
    assert ranges.not_contains(r, "a") is True
    assert sink == [Downgrade(name="__contains__"), Downgrade(name="__contains__")]


def test_python_s_own_in_tests_the_answer_where_it_runs() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(3, sink, "n"))

    assert (5 in r) is False
    assert [(fork.expression, fork.taken) for fork in sink if isinstance(fork, Branch)] == [
        (["in", 5, ["range", 0, "n"]], False)
    ]


def test_every_untaught_operation_is_range_s_answer_and_a_downgrade() -> None:
    sink: list[SinkItem] = []

    answers = _probe("untaught", _range(_int(3, sink, "n")))

    assert answers == [3, 0, [2, 1, 0], 1, 1, True]
    assert sink == [
        Downgrade(name=name)
        for name in ("__len__", "__getitem__", "__reversed__", "count", "index", "__bool__")
    ]


def test_an_untaught_operation_python_refuses_raises_as_the_target_s() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(2, sink, "n"))

    with pytest.raises(IndexError) as raised:
        r[5]  # pyrefly: ignore[bad-index]

    with pytest.raises(IndexError) as plain:
        range(2)[5]
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


# ranges of every shape two ranges can be equal in: empty ones with other bounds, one-element
# ones with other steps, and longer ones with a start, a stop or a step apart
_SHAPES = [
    (2,),
    (0, 2),
    (0, 3),
    (1, 3),
    (5, 5),
    (7, 3),
    (4, 5),
    (4, 5, 9),
    (0, 4, 2),
    (0, 3, 2),
    (3, 0, -1),
]


def _tracked_range(bounds: tuple[int, ...], sink: list[SinkItem], name: str) -> ConcolicRange:
    """A range with its first bound tracked, named ``name``."""
    return _range(_int(bounds[0], sink, name), *bounds[1:])


@pytest.mark.parametrize(("left", "right"), list(itertools.product(_SHAPES, repeat=2)))
def test_two_ranges_compare_as_python_compares_them(
    left: tuple[int, ...], right: tuple[int, ...]
) -> None:
    sink: list[SinkItem] = []
    a, b = _tracked_range(left, sink, "a"), _tracked_range(right, sink, "b")
    same = range(*left) == range(*right)

    plain_left = range(*left) == b
    for answer, expected in (
        (a == b, same),
        (a != b, not same),
        (a == range(*right), same),
        (plain_left, same),
    ):
        assert type(answer) is ConcolicBool
        assert int.__index__(answer) == expected
    # an answer handed back untested records nothing until the target tests it
    assert sink == []


def test_an_equality_of_two_ranges_is_one_fork_on_their_arguments() -> None:
    sink: list[SinkItem] = []
    a, b = _range(_int(2, sink, "n")), _range(0, _int(2, sink, "m"), 1)

    answer = a == b

    assert isinstance(answer, ConcolicBool)
    assert answer.expression == ["==", ["range", 0, "n"], ["range", 0, "m", 1]]
    unequal = a != b
    assert isinstance(unequal, ConcolicBool)
    assert unequal.expression == ["!=", ["range", 0, "n"], ["range", 0, "m", 1]]
    assert len({a, b}) == 1


def test_a_range_equals_nothing_but_a_range_as_python_s_does() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(2, sink, "n"))

    assert (r == [0, 1]) is False and (r != (0, 1)) is True
    assert sink == []


def test_an_order_between_ranges_raises_as_python_s_does() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(TypeError) as raised:
        assert _range(_int(2, sink, "n")) < _range(_int(3, sink, "m"))  # pyrefly: ignore
    with pytest.raises(TypeError) as plain:
        assert range(2) < range(3)  # pyrefly: ignore[unsupported-operation]
    # Python names the two types, and a tracked range's is its own
    assert str(raised.value) == str(plain.value).replace("'range'", "'ConcolicRange'")
    assert sink == []


def test_a_range_is_a_sequence_as_python_s_is() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(5, sink, "n"))

    assert isinstance(r, Sequence)
    assert random.Random(0).sample(r, 2) == random.Random(0).sample(range(5), 2)


def test_a_match_reads_a_range_as_a_sequence() -> None:
    sink: list[SinkItem] = []
    namespace: dict[str, object] = {}
    exec(
        "def shape(r):\n    match r:\n        case [a, b, c]:\n            return (a, b, c)\n"
        "        case _:\n            return None\n",
        namespace,
    )
    shape = namespace["shape"]
    assert callable(shape)

    assert shape(_range(_int(3, sink, "n"))) == shape(range(3)) == (0, 1, 2)


def test_a_length_past_the_largest_size_raises_the_target_s_overflow() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(10**23, sink, "n"))

    with pytest.raises(OverflowError) as raised:
        len(r)

    with pytest.raises(OverflowError) as plain:
        len(range(10**23))
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)


def test_every_method_range_defines_is_taught_kept_or_derived() -> None:
    # every method range calls on a value, but object's own attribute lookup, which stays
    methods = {
        name
        for name, member in vars(range).items()
        if callable(member) and name not in ("__new__", "__getattribute__")
    }
    assert methods <= set(vars(ConcolicRange))


def test_hash_and_repr_stay_range_s() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(1, sink, "a"), 5, 2)

    assert repr(r) == "range(1, 5, 2)"
    assert hash(r) == hash(range(1, 5, 2))
    assert sink == []


def test_a_copy_is_the_range_itself_and_a_pickle_holds_python_s() -> None:
    sink: list[SinkItem] = []
    r = _range(_int(3, sink, "n"))

    assert copy.copy(r) is r and copy.deepcopy(r) is r
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(r, protocol)) == range(3)
    assert sink == [Downgrade(name="__reduce_ex__")] * (pickle.HIGHEST_PROTOCOL + 1)


def test_the_attributes_are_the_arguments_the_target_passed() -> None:
    sink: list[SinkItem] = []
    a = _int(1, sink, "a")
    r = _range(a, 7, _int(2, sink, "k"))

    assert r.start is a and r.stop == 7 and type(r.stop) is int
    assert isinstance(r.step, ConcolicInt) and r.step.expression == "k"
    one = _range(_int(4, sink, "n"))
    assert (one.start, one.step) == (0, 1) and one.stop.expression == "n"  # pyrefly: ignore
    # the step's own two forks, and no downgrade
    assert all(isinstance(item, Branch) for item in sink)
