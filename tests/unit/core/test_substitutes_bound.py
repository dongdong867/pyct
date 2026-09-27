"""What a bound `len`, `ord` and `chr` call: Python's own on plain values, core's on tracked."""

import builtins
import inspect
import pickle
from collections.abc import Callable

import pytest

from pyct.core import bound as bound_module
from pyct.core.bound import BOUND
from pyct.core.branch import Branch, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.substitutes import PASSING

len_, ord_, chr_ = (BOUND[name][1] for name in ("len", "ord", "chr"))

Call = tuple[tuple[object, ...], dict[str, object]]


def outcome(function: Callable[..., object], call: Call) -> tuple[str, object]:
    """What one call gives: its answer and the answer's type, or its raise's type and message."""
    args, kwargs = call
    try:
        answer = function(*args, **kwargs)
    except Exception as error:
        return "raised", (type(error), str(error))
    return "answered", (type(answer), answer)


@pytest.mark.parametrize(
    ("python", "call"),
    [
        (len, (("ab",), {})),
        (len, ((["a", "b", "c"],), {})),
        (len, (({"k": 1},), {})),
        (len, ((5,), {})),
        (len, ((), {})),
        (len, (("a", "b"), {})),
        (len, ((), {"obj": "a"})),
        (len, (("a",), {"x": 1})),
        (len, ((ConcolicInt(5, expression="n", sink=[]),), {})),
        (len, ((ConcolicFloat(0.5, expression="f", sink=[]),), {})),
        (ord, (("a",), {})),
        (ord, (("ab",), {})),
        (ord, ((b"a",), {})),
        (ord, ((97,), {})),
        (ord, ((), {"c": "a"})),
        (ord, ((ConcolicInt(5, expression="n", sink=[]),), {})),
        (chr, ((98,), {})),
        (chr, ((-1,), {})),
        (chr, ((1114112,), {})),
        (chr, (("a",), {})),
        (chr, ((True,), {})),
        (chr, ((2**70,), {})),
        (chr, ((), {"i": 98})),
        (chr, ((ConcolicStr("a", expression="s", sink=[]),), {})),
    ],
)
def test_a_bound_builtin_is_python_s_own_on_every_other_call(
    python: Callable[..., object], call: Call
) -> None:
    bound = {name: pyct for name, (_, pyct) in BOUND.items()}[python.__name__]

    assert outcome(bound, call) == outcome(python, call)


def test_a_bound_len_asks_the_value_s_own_len_once_as_python_does() -> None:
    log: list[str] = []

    class Sized:
        def __len__(self) -> int:
            log.append("__len__")
            return 4

    assert len_(Sized()) == 4
    assert log == ["__len__"]


def test_a_bound_len_on_a_tracked_string_is_its_tracked_length() -> None:
    sink: list[SinkItem] = []

    size = len_(ConcolicStr("abcd", expression="s", sink=sink))

    assert type(size) is ConcolicInt
    assert size.expression == ["len", "s"]
    assert sink == []


def test_a_bound_len_through_map_measures_each_item() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("ab", expression="s", sink=sink)

    sizes = list(map(len_, [s, "xyz"]))

    assert [int.__int__(size) for size in sizes if isinstance(size, int)] == [2, 3]
    assert [getattr(size, "expression", None) for size in sizes] == [["len", "s"], None]
    assert sink == []


def test_bound_ord_and_chr_on_tracked_values_are_core_s() -> None:
    sink: list[SinkItem] = []

    code = ord_(ConcolicStr("a", expression="c", sink=sink))
    character = chr_(ConcolicInt(98, expression="n", sink=sink))

    assert isinstance(code, ConcolicInt) and isinstance(character, ConcolicStr)
    assert (int.__int__(code), code.expression) == (97, ["ord", "c"])
    assert (str.__str__(character), character.expression) == ("b", ["chr", "n"])
    assert [(item.expression, item.taken) for item in sink if isinstance(item, Branch)] == [
        (["==", ["len", "c"], 1], True),
        ([">=", "n", 0], True),
        (["<=", "n", 1114111], True),
    ]


def test_the_bound_names_are_the_three_builtins() -> None:
    assert dict(BOUND) == {"len": (len, len_), "ord": (ord, ord_), "chr": (chr, chr_)}


def test_the_passing_frames_are_the_routers() -> None:
    assert {code.co_name for code in PASSING} == {
        "is_",
        "is_not",
        "in_",
        "not_in",
        "len",
        "ord",
        "chr",
        "_routed",
    }


@pytest.mark.parametrize("name", ["len", "ord", "chr"])
def test_a_bound_builtin_calls_python_s_own_when_builtins_holds_another(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    python, bound = BOUND[name]
    argument = {"len": "ab", "ord": "a", "chr": 98}[name]
    calls: list[object] = []

    def replaced(*args: object, **kwargs: object) -> object:
        calls.append(args)
        return python(*args, **kwargs)

    # every builtin replaced, as a target or a mock may replace them after the module loaded
    for each, (own_python, _) in BOUND.items():
        monkeypatch.setattr(builtins, each, replaced if each == name else own_python)
    answer = outcome(bound, ((argument,), {}))
    tracked = outcome(bound, ((ConcolicStr("a", expression="s", sink=[]),), {}))
    monkeypatch.undo()

    # a module that found the bound function keeps it, as plain Python keeps the builtin it
    # found, and it answers as Python's own without asking what builtins holds now
    assert answer == outcome(python, ((argument,), {}))
    assert tracked[0] == outcome(python, (("a",), {}))[0]
    assert calls == []


@pytest.mark.parametrize("name", ["len", "ord", "chr"])
def test_a_bound_builtin_looks_like_python_s_own(name: str) -> None:
    python, bound = BOUND[name]

    # its module is its own, so pickle finds it by name as it finds Python's
    assert (bound.__name__, bound.__qualname__, bound.__module__) == (name, name, "pyct.core.bound")
    assert getattr(bound_module, name) is bound
    assert bound.__doc__ == python.__doc__
    text_signature = "__text_signature__"
    assert getattr(bound, text_signature, None) == getattr(python, text_signature)
    assert inspect.signature(bound) == inspect.signature(python)


@pytest.mark.parametrize("name", ["len", "ord", "chr"])
def test_a_bound_builtin_pickles_by_reference_as_python_s_does(name: str) -> None:
    python, bound = BOUND[name]

    assert pickle.loads(pickle.dumps(bound)) is bound
    assert pickle.loads(pickle.dumps({"f": [bound]})) == {"f": [bound]}
    assert pickle.loads(pickle.dumps(python)) is python
