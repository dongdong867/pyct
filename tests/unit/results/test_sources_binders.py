"""Each statement that binds a name ends the reach of the name's earlier bindings, and only the
paths that can run on past a statement carry their bindings beyond it."""

from pathlib import Path

import pytest

from tests.unit.results.test_sources import loop, module, sources

FINALLY_REPLACED = """\
def logged(s, x):
    t = 0
    for c in s:
        t += 1
    try:
        t = int(x)
    except ValueError:
        t = 0
    finally:
        log()
    if t > 3:
        return 1
    return 0
"""


def test_only_the_path_that_ends_normally_runs_past_a_finally(tmp_path: Path) -> None:
    file = module(tmp_path, FINALLY_REPLACED)

    assert sources(file, "logged", (11, 7)) == ()


CAUGHT_AS = """\
def caught(items, x):
    for e in items:
        pass
    try:
        x = int(x)
    except ValueError as e:
        if e.args:
            return 1
    return 0
"""

DEFINED_AGAIN = """\
def defined_again(items):
    for helper in items:
        pass

    def helper():
        return 1

    if helper():
        return 1
    return 0
"""

CLASS_AGAIN = """\
def class_again(items):
    for Box in items:
        pass

    class Box:
        size = 1

    if Box.size:
        return 1
    return 0
"""

IMPORTED = """\
def imported(items):
    for json in items:
        pass
    import json
    if json.loads("1"):
        return 1
    return 0
"""

CAPTURED = """\
def captured(items, k):
    for v in items:
        pass
    match k:
        case [v] | {"k": 1, **v}:
            if v > 3:
                return 1
    return 0
"""

EVERY_CASE = """\
def every_case(s, k):
    t = 0
    for c in s:
        t += 1
    match k:
        case 1:
            t = 1
        case _:
            t = 2
    if t > 25:
        return 1
    return 0
"""

EVERY_CAPTURE = """\
def every_capture(s, k):
    t = 0
    for c in s:
        t += 1
    match k:
        case 1:
            t = 1
        case other:
            t = 2
    if t > 25:
        return 1
    return 0
"""

SUPPRESSED = """\
def suppressed(s, f):
    t = 0
    for c in s:
        t += 1
    with suppress(ValueError):
        t = int(f)
    if t > 25:
        return 1
    return 0
"""

DEFINED_IN_A_LOOP = """\
def defined_in_a_loop(names, x):
    for name in names:

        def check(v, name=name):
            return v == name

    if check(x):
        return 1
    if name == x:
        return 2
    return 0
"""


@pytest.mark.parametrize(
    ("source", "function", "at", "expected"),
    [
        pytest.param(CAUGHT_AS, "caught", (7, 11), (), id="an except's name"),
        pytest.param(DEFINED_AGAIN, "defined_again", (8, 7), (), id="a def's name"),
        pytest.param(CLASS_AGAIN, "class_again", (8, 7), (), id="a class's name"),
        pytest.param(IMPORTED, "imported", (5, 7), (), id="an import's name"),
        pytest.param(CAPTURED, "captured", (6, 15), (), id="a case's capture"),
        pytest.param(EVERY_CASE, "every_case", (10, 7), (), id="a last case _"),
        pytest.param(EVERY_CAPTURE, "every_capture", (10, 7), (), id="a last bare capture"),
        pytest.param(SUPPRESSED, "suppressed", (7, 7), (("t", 3, 4),), id="a with that suppresses"),
        pytest.param(DEFINED_IN_A_LOOP, "defined_in_a_loop", (7, 7), (), id="a def in a loop"),
        pytest.param(
            DEFINED_IN_A_LOOP,
            "defined_in_a_loop",
            (9, 7),
            (("name", 2, 4),),
            id="its loop's target",
        ),
    ],
)
def test_each_binder_ends_an_earlier_binding_s_reach(
    tmp_path: Path,
    source: str,
    function: str,
    at: tuple[int, int],
    expected: tuple[tuple[str, int, int], ...],
) -> None:
    file = module(tmp_path, source)

    assert sources(file, function, at) == tuple(loop(file, *each) for each in expected)
