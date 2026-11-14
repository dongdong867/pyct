"""The hooks around a piece of the target's code hand back what the code needs, and while an
input is live record the first runs of each piece: what its names held going in and what its
changed names held at its end."""

import contextlib
from collections.abc import Callable, Iterator
from typing import cast

import pytest

from pyct.core.entry import pieces, substitutes
from pyct.core.entry.pieces import piece_in, piece_out, piece_over, piece_value
from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, SinkItem, Site
from pyct.core.numbers.ints import ConcolicInt
from pyct.intercept.compiled import substituted_code
from pyct.intercept.loops import BOUND
from tests.unit.intercept.loop_shapes import ASSIGNMENTS, LOOPS

SITE = (3, 4, ("t", "xs"), ("t",))
FILE = "<pieces>"


def test_each_hook_hands_back_what_the_code_needs() -> None:
    iterable, value = [1, 2], object()

    assert piece_over(iterable, *SITE) is iterable
    assert piece_value(piece_in(*SITE), value) is value
    assert piece_out(*SITE) is None


def test_the_hooks_are_not_among_what_every_substituted_module_imports() -> None:
    # a module compiled with the pieces switch on imports them from here itself
    assert not any(hasattr(substitutes, name) for name in BOUND.values())


def hooked(source: str, **names: object) -> Callable[..., object]:
    """The source's `f`, compiled with the pieces switch on."""
    namespace: dict[str, object] = {"g": lambda *_: None, **names}
    exec(substituted_code(source.encode(), FILE, pieces=True), namespace)  # noqa: S102
    function = namespace["f"]
    assert callable(function)
    return function


@contextlib.contextmanager
def live() -> Iterator[list[SinkItem]]:
    """A live input whose sink is the list yielded, while the block lasts."""
    sink: list[SinkItem] = []
    pieces.start(sink)
    try:
        yield sink
    finally:
        pieces.forget()


def run(line: int, col: int, going_in: dict[str, str], changed: dict[str, str]) -> PieceRun:
    """A recorded run of the piece at the line and column, none of its values tracked."""
    return PieceRun(
        site=Site(file=FILE, line=line, col=col),
        going_in=tuple(GoingIn(name, value, tracked=False) for name, value in going_in.items()),
        changed=tuple(Changed(name, value) for name, value in changed.items()),
    )


def recorded(sink: list[SinkItem]) -> list[PieceRun]:
    """The recorded runs in the sink, in order."""
    return [item for item in sink if isinstance(item, PieceRun)]


def test_a_hook_called_while_no_input_is_live_records_nothing() -> None:
    f = hooked(LOOPS["for"])
    sink: list[SinkItem] = []
    pieces.start(sink)
    pieces.forget()

    assert f([1, 2]) == 3
    assert sink == []


def test_a_for_loop_records_its_names_going_in_at_its_start_and_its_changed_names_at_its_end() -> (
    None
):
    f = hooked(LOOPS["for"])

    with live() as sink:
        f([1, 2])

    assert sink == [run(3, 4, {"t": "0", "xs": "[1, 2]"}, {"t": "3"})]


def test_a_while_and_an_assignment_of_a_comprehension_record_their_runs() -> None:
    with live() as sink:
        hooked(LOOPS["while"])(2)
        hooked(ASSIGNMENTS["listcomp"])("ab")

    assert sink == [
        run(3, 4, {"i": "0", "n": "2"}, {"i": "2"}),
        run(2, 8, {"s": '"ab"'}, {"u": '["a", "b"]'}),
    ]


def test_a_while_true_and_a_for_record_a_run_that_ends_by_a_break() -> None:
    with live() as sink:
        hooked(LOOPS["while_true_break"])(1)
        hooked(LOOPS["for_else_break"])([1, 3, 5])

    assert sink == [
        run(3, 4, {"i": "0", "n": "1"}, {"i": "2"}),
        run(2, 4, {"xs": "[1, 3, 5]"}, {"x": "3"}),
    ]


FOR_ELSE = """\
def f(xs):
    last = None
    t = 0
    for x in xs:
        if x < 0:
            break
        t += x
    else:
        last = t
    return t, last
"""
WHILE_ELSE = """\
def f(n):
    i = 0
    done = False
    while i < n:
        if i == 5:
            break
        i += 1
    else:
        done = True
    return i, done
"""
READ_IN_ELSE = """\
def f(xs):
    for x in xs:
        y = x * 2
    else:
        return y
    return None
"""


def test_a_loop_s_else_is_not_its_own_and_it_records_the_loop_s_values_however_it_ends() -> None:
    # each loop in an input of its own, since two of them share a site
    with live() as for_else:
        assert hooked(FOR_ELSE)([1, 2]) == (3, 3)
        assert hooked(FOR_ELSE)([1, -1]) == (1, None)
    with live() as while_else:
        assert hooked(WHILE_ELSE)(2) == (2, True)
        assert hooked(WHILE_ELSE)(9) == (5, False)
    with live() as read_in_else:
        assert hooked(READ_IN_ELSE)([1, 2]) == 4

    # the else's names are not the loop's; one the loop binds that its else reads is
    assert for_else + while_else + read_in_else == [
        run(4, 4, {"t": "0", "xs": "[1, 2]"}, {"t": "3"}),
        run(4, 4, {"t": "0", "xs": "[1, -1]"}, {"t": "1"}),
        run(4, 4, {"i": "0", "n": "2"}, {"i": "2"}),
        run(4, 4, {"i": "0", "n": "9"}, {"i": "5"}),
        run(2, 4, {"xs": "[1, 2]"}, {"y": "4"}),
    ]


def test_only_the_first_three_runs_of_a_piece_in_an_input_are_recorded() -> None:
    f = hooked(LOOPS["while"])

    with live() as sink:
        for n in range(5):
            f(n)
    with live() as again:
        f(7)

    assert [each.going_in[1].value for each in recorded(sink)] == ["0", "1", "2"]
    assert [each.changed for each in recorded(again)] == [(Changed("i", "7"),)]


def test_a_run_that_ends_by_return_or_a_raise_records_nothing_and_still_counts() -> None:
    f = hooked(LOOPS["return_raise_in_body"])

    with live() as sink:
        assert f([0, 5]) == 5
        with pytest.raises(ValueError):
            f([None])
        assert f([0, 0]) == 0
        assert f([0]) == 0

    # the first two runs ended early; the third ran out, and the fourth is past the three
    assert sink == [run(2, 4, {"xs": "[0, 0]"}, {"x": "0"})]


def test_a_name_not_bound_when_the_piece_starts_or_ends_is_left_out() -> None:
    source = (
        "def f(xs, c):\n    if c:\n        t = 0\n    for x in xs:\n        t += x\n    return t\n"
    )
    with_t = "def f(xs):\n    for x in xs:\n        t = x\n    return t\n"

    with live() as sink:
        with contextlib.suppress(UnboundLocalError):
            hooked(source)([], False)
        with contextlib.suppress(UnboundLocalError):
            hooked(with_t)([])

    assert sink == [run(4, 4, {"xs": "[]"}, {}), run(2, 4, {"xs": "[]"}, {})]


MANGLED = """\
class C:
    def f(self, xs):
        __t = 0
        for x in xs:
            __t += x
        return __t
"""


def test_a_name_python_stores_under_another_spelling_is_left_out_as_an_unbound_one() -> None:
    namespace: dict[str, object] = {}
    exec(substituted_code(MANGLED.encode(), FILE, pieces=True), namespace)  # noqa: S102
    made = namespace["C"]
    assert isinstance(made, type)

    with live() as sink:
        assert made().f([1, 2]) == 3

    # the frame holds `_C__t`, which the hooks, given `__t`, do not read
    assert sink == [run(4, 8, {"xs": "[1, 2]"}, {})]


def test_a_value_json_cannot_hold_or_one_too_long_leaves_that_run_unrecorded() -> None:
    f = hooked(LOOPS["while_not"], g=lambda: "z")

    with live() as sink:
        f({1})
        f("x" * 2046)
        f("")

    # a value's text is under 2 KB, and "x" * 2046 written as JSON takes 2048 characters
    assert sink == [run(2, 4, {"s": '""'}, {"s": '"z"'})]


def test_a_changed_value_json_cannot_hold_leaves_that_run_unrecorded() -> None:
    f = hooked(LOOPS["while_not"], g=lambda: (1,))

    with live() as sink:
        f(None)

    assert sink == []


def test_a_tracked_value_going_in_is_marked_tracked_and_kept_as_its_plain_value() -> None:
    with live() as sink:
        hooked(LOOPS["for"])([ConcolicInt.made(2, expression="x", sink=[]), 3])
        hooked(LOOPS["while"])(ConcolicInt.made(1, expression="n", sink=[]))

    # a plain list is not tracked, whatever it holds
    assert [each.going_in for each in recorded(sink)] == [
        (GoingIn("t", "0", tracked=False), GoingIn("xs", "[2, 3]", tracked=False)),
        (GoingIn("i", "0", tracked=False), GoingIn("n", "1", tracked=True)),
    ]
    assert recorded(sink)[0].changed == (Changed("t", "5"),)


def test_a_list_the_loop_changes_in_place_goes_in_as_it_was_at_the_start() -> None:
    source = "def f(xs):\n    for x in [1, 2]:\n        xs.append(x)\n    return xs, x\n"

    with live() as sink:
        assert hooked(source)([]) == ([1, 2], 2)

    assert sink == [run(2, 4, {"xs": "[]"}, {"x": "2"})]


RECURSIVE = """\
def f(n):
    t = 0
    for x in range(n):
        t += f(x)
    return t + 1
"""


def test_each_call_of_a_recursion_pairs_its_own_start_with_its_own_end() -> None:
    with live() as sink:
        hooked(RECURSIVE)(2)

    # f(2)'s run starts first, then f(0)'s and f(1)'s; the f(0) f(1) calls is the fourth
    assert sink == [
        run(3, 4, {"n": "0", "t": "0"}, {"t": "0"}),
        run(3, 4, {"n": "1", "t": "0"}, {"t": "1"}),
        run(3, 4, {"n": "2", "t": "0"}, {"t": "3"}),
    ]


def test_two_generators_suspended_in_one_loop_keep_their_runs_apart() -> None:
    f = hooked(LOOPS["generator"])

    with live() as sink:
        first, second = cast(Iterator[int], f([1, 2])), cast(Iterator[int], f([10]))
        next(first)
        next(second)
        list(second)
        list(first)

    assert sink == [
        run(3, 4, {"t": "0", "xs": "[10]"}, {"t": "10"}),
        run(6, 4, {"t": "10"}, {"t": "0"}),
        run(3, 4, {"t": "0", "xs": "[1, 2]"}, {"t": "3"}),
        run(6, 4, {"t": "3"}, {"t": "0"}),
    ]


def test_nested_loops_keep_their_runs_apart() -> None:
    with live() as sink:
        hooked(LOOPS["nested_break_in_else"])([[0, 1], [2]])

    assert sink == [
        run(4, 8, {"n": "0", "xs": "[0, 1]"}, {"n": "1"}),
        run(4, 8, {"n": "0", "xs": "[2]"}, {"n": "0"}),
        run(3, 4, {"n": "0", "xss": "[[0, 1], [2]]"}, {"n": "-1"}),
    ]


def test_a_run_left_by_a_return_is_dropped_by_the_next_start_in_its_frame() -> None:
    source = "def f(xs):\n    for x in xs:\n        if x:\n            return x\n    return x\n"
    f = hooked(source)

    with live() as sink:
        f([1])
        f([0])

    assert sink == [run(2, 4, {"xs": "[0]"}, {"x": "0"})]


def test_hooks_given_no_names_hand_back_their_values_and_record_the_first_runs() -> None:
    with live() as sink:
        for _ in range(5):
            assert piece_over([1], 7, 4, (), ()) == [1]
            piece_out(7, 4, (), ())

    assert [(each.site.line, each.going_in, each.changed) for each in recorded(sink)] == [
        (7, (), ())
    ] * 3


def test_an_exit_with_no_start_records_nothing() -> None:
    with live() as sink:
        piece_out(*SITE)
        assert piece_value(None, 5) == 5

    assert sink == []


def test_runs_past_the_text_an_input_keeps_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    f = hooked(LOOPS["while"])
    one = run(3, 4, {"i": "0", "n": "1"}, {"i": "1"})
    monkeypatch.setattr(pieces, "MOST_TEXT", 2 * pieces.size(one) + 1)

    with live() as sink:
        f(1)
        f(22)
        f(3)

    # the second run's two-digit values take it past what is left
    assert [each.changed for each in recorded(sink)] == [(Changed("i", "1"),), (Changed("i", "3"),)]
