"""Only a binding that can run before a condition, with no other binding of its name in between,
feeds it, and a loop around the condition is read through, never named."""

import sys
from pathlib import Path

import pytest

from pyct.results.graphs import OutOfTimeError
from pyct.results.sources import Origins
from tests.unit.results.test_sources import code_named, loop, lost, module, sources

AFTER = """\
def after(s):
    t = helper(s)
    if t == 3:
        return "three"
    for c in s:
        t += 1
    return t
"""


def test_a_loop_that_runs_after_the_condition_is_not_its_source(tmp_path: Path) -> None:
    file = module(tmp_path, AFTER)

    assert sources(file, "after", (3, 7)) == ()


AROUND = """\
def around(n, base, s, t):
    b = pow(base, t, n)
    if b == 1 or b == n - 1:
        return True
    for _ in range(s - 1):
        b = pow(b, 2, n)
        if b == n - 1:
            return True
        if b == 1:
            return False
    return False
"""


def test_a_loop_around_the_condition_is_read_through_to_the_loss(tmp_path: Path) -> None:
    file = module(tmp_path, AROUND)

    found = sources(file, "around", (9, 11), {(2, 8): ("pow",)})

    assert found == (lost(file, "base", "pow", 2, 8),)


def test_a_loss_inside_the_loop_around_the_condition_ends_the_path(tmp_path: Path) -> None:
    file = module(tmp_path, AROUND)

    found = sources(file, "around", (9, 11), {(2, 8): ("pow",), (6, 12): ("pow",)})

    assert found == (lost(file, "b", "pow", 6, 12),)


REPLACED = """\
def replaced(n):
    for d in divisors(n):
        y = 2 * d
    for d in divisors(2 * n - 1):
        if n > d:
            yield d
    for d in divisors(2 * n + 1):
        if n > d >= 2 and n % d:
            yield d
"""


def test_a_binding_another_always_replaces_first_gives_no_source(tmp_path: Path) -> None:
    file = module(tmp_path, REPLACED)

    # the loop at line 7 binds d before its body, and it encloses the condition
    assert sources(file, "replaced", (8, 26)) == ()


OWN_TEST = """\
def own_test(n):
    if not n % 3:
        n //= 3
        m = 1
        while not n % 3:
            n //= 3
            m += 1
        factors = m
    p = 5
    while p < 100:
        while not n % p:
            n //= p
        p += 2
    return n
"""


def test_a_loop_s_own_test_is_fed_neither_by_it_nor_by_later_loops(tmp_path: Path) -> None:
    file = module(tmp_path, OWN_TEST)

    assert sources(file, "own_test", (5, 18)) == ()


OPTIONS = """\
def options(rest):
    while True:
        if rest[:1] == '"':
            pos = 1
            while pos < len(rest):
                if rest[pos] == '"':
                    rest = rest[pos + 1 :]
                    break
                pos += 1
        if (end := rest.find(";")) == -1:
            break
        rest = rest[end + 1 :].lstrip()
    return rest
"""


def test_a_loop_inside_the_loop_around_the_condition_can_be_its_source(tmp_path: Path) -> None:
    file = module(tmp_path, OPTIONS)

    assert sources(file, "options", (10, 11)) == (loop(file, "rest", 5, 12),)


BRANCHES = """\
def branches(s, k):
    t = 0
    for c in s:
        t += 1
    u = t
    if k > 0:
        t = 1
        u = 1
    else:
        t = 2
    if t > 25:
        return 1
    if u > 25:
        return 2
    return 0
"""


def test_both_branches_binding_again_end_a_loop_s_reach(tmp_path: Path) -> None:
    file = module(tmp_path, BRANCHES)

    assert sources(file, "branches", (11, 7)) == ()
    # only the if binds u again, so the else keeps the value the loop made
    assert sources(file, "branches", (13, 7)) == (loop(file, "t", 3, 4),)


REBOUND = """\
def rebound(s):
    t = 0
    for c in s:
        t += 1
    t = len(s)
    if t > 25:
        return 1
    return 0
"""


def test_a_name_rebound_after_a_loop_does_not_come_from_it(tmp_path: Path) -> None:
    file = module(tmp_path, REBOUND)

    assert sources(file, "rebound", (6, 7)) == ()


NESTED = """\
def nested(rows):
    t = 0
    for row in rows:
        for c in row:
            t += 1
    if t > 25:
        return 1
    for c in rows:
        t += 2
    return t
"""


def test_nested_loops_before_the_condition_name_the_innermost(tmp_path: Path) -> None:
    file = module(tmp_path, NESTED)

    assert sources(file, "nested", (6, 7)) == (loop(file, "t", 4, 8),)


TRIED = """\
def tried(s):
    t = 0
    try:
        for c in s:
            t += 1
        t = 0
    except ValueError:
        pass
    if t > 25:
        return 1
    for c in s:
        t += 2
    return t
"""


def test_a_handler_starts_from_any_binding_its_try_made(tmp_path: Path) -> None:
    file = module(tmp_path, TRIED)

    # the loop can raise before t = 0 runs
    assert sources(file, "tried", (9, 7)) == (loop(file, "t", 4, 8),)


FOREVER = """\
def forever(s):
    t = 0
    for c in s:
        t += 1
    while True:
        t = len(s)
        break
    if t > 25:
        return 1
    return 0
"""


def test_a_while_true_loop_is_left_only_through_a_break(tmp_path: Path) -> None:
    file = module(tmp_path, FOREVER)

    assert sources(file, "forever", (8, 7)) == (loop(file, "t", 5, 4),)


WALRUS = """\
def walrused(s):
    t = 0
    for c in s:
        t += 1
    if (n := t) > 3 and n < 10:
        return 1
    for c in s:
        t -= 1
    return t
"""


def test_a_walrus_binds_where_it_is_evaluated(tmp_path: Path) -> None:
    file = module(tmp_path, WALRUS)

    assert sources(file, "walrused", (5, 24)) == (loop(file, "t", 3, 4),)


def test_a_stop_that_comes_while_the_function_is_walked_ends_the_reading(tmp_path: Path) -> None:
    file = module(tmp_path, NESTED)

    def stop_in_the_walk() -> None:
        if sys._getframe(1).f_code.co_filename.endswith("reaching.py"):
            raise OutOfTimeError

    with pytest.raises(OutOfTimeError):
        Origins(file, {}, step=stop_in_the_walk).of(code_named(file, "nested"), 6, 7)


WITHED = """\
def withed(s, f):
    t = 0
    for c in s:
        t += 1
    with lock, open(f) as t:
        pass
    if t:
        return 1
    return 0
"""

MATCHED = """\
def matched(s, k):
    t = 0
    match k:
        case 1 if t == 0:
            for c in s:
                t += 1
        case 2:
            pass
    if t > 25:
        return 1
    return 0
"""

FINISHED = """\
def finished(s, k):
    t = 0
    try:
        for c in s:
            t += 1
        return t
        t = 0
    finally:
        if t > 25:
            k = 1
"""

CLEANED = """\
def cleaned(s):
    t = 0
    try:
        t = len(s)
    except:
        for c in s:
            t += 1
    finally:
        u = t
    if u > 25:
        return 1
    return 0
"""

SKIPPED = """\
def skipped(s):
    t = 0
    for c in s:
        t = len(s)
        if c == "a":
            for d in s:
                t += 1
            continue
        t = 0
    if t > 25:
        return 1
    return 0
"""

DEFINED = """\
def defined(s):
    t = 0
    for c in s:
        t += 1

    @decorate(lambda: t)
    def inner(x=t, *, y):
        return (t := x)

    class Box(Base, meta=t):
        size = (t := 1)

    if t > 25:
        return 1
    return 0
"""

LAMBDA = """\
picks = lambda s: 1 if sum(1 for c in s) > 3 else 0
"""

SKIPPABLE = """\
def skippable(s, k):
    t = 0
    for c in s:
        t += 1
    keys = {c: (t := len(s)) for c in s}
    if k > 0 and (t := 3):
        return 1
    if t > 25:
        return 2
    return keys
"""


@pytest.mark.parametrize(
    ("source", "function", "at", "expected"),
    [
        pytest.param(WITHED, "withed", (7, 7), (), id="a with's name"),
        pytest.param(MATCHED, "matched", (9, 7), (("t", 5, 12),), id="a case's body"),
        pytest.param(FINISHED, "finished", (9, 11), (("t", 4, 8),), id="finally, after a return"),
        pytest.param(CLEANED, "cleaned", (10, 7), (("t", 6, 8),), id="a bare handler"),
        pytest.param(SKIPPED, "skipped", (10, 7), (("t", 3, 4), ("t", 6, 12)), id="a continue"),
        pytest.param(DEFINED, "defined", (13, 7), (("t", 3, 4),), id="another scope's walrus"),
        pytest.param(LAMBDA, "<lambda>", (1, 23), (("s", 1, 26),), id="a lambda"),
        pytest.param(
            SKIPPABLE, "skippable", (8, 7), (("t", 3, 4),), id="a walrus that can be skipped"
        ),
    ],
)
def test_each_kind_of_statement_is_walked_in_the_order_it_runs(
    tmp_path: Path,
    source: str,
    function: str,
    at: tuple[int, int],
    expected: tuple[tuple[str, int, int], ...],
) -> None:
    file = module(tmp_path, source)

    assert sources(file, function, at) == tuple(loop(file, *each) for each in expected)


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
