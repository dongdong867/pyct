"""Witness tests for Python built-in tracking through the Concolic layer.

These tests exist to catch **wiring regressions** where Python's built-in
functions (``len``, ``int``, ``str``, ``bool``) lose their symbolic routing.
The ``environment_preparer`` gap in M2-B.2b was silent for a full session
because no existing fixture exercised ``len()`` in a branch predicate —
these witnesses make that class of regression loud on the next run.

Each target shapes its only-alternate-arm path around the builtin being
tested. The assertions check both that a plausible number of paths were
explored **and** that a specific alternate-arm source line is present in
``executed_lines``. The line-level check discriminates real symbolic
synthesis from lucky randomness: coverage percent can pass when
exploration hits multiple lines by accident, but a specific line gets
covered only when the solver produced the input that drives it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable


def test_len_drives_alternate_arm():
    """
    Given a target whose 'long' arm requires len(s) > 5
    When run_concolic starts from an empty seed string
    Then the engine synthesizes both a short and a >5 long string
      And the len-gated alternate arm line is in executed_lines
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.builtins.length_check import check_length

    result = run_concolic(target=check_length, initial_args={"s": ""})

    assert result.success
    assert result.paths_explored >= 3
    long_arm_line = _find_return_line(check_length, "long")
    assert long_arm_line in result.executed_lines, (
        f"line {long_arm_line} not in {sorted(result.executed_lines)} — "
        "builtins.len monkey-patch may have been dropped"
    )


def test_int_drives_alternate_arm():
    """
    Given a target whose 'zero' arm requires int(s) == 0
    When run_concolic starts from a nonzero seed string
    Then the engine synthesizes a string that parses to 0
      And the int-gated alternate arm line is in executed_lines
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.builtins.int_parse import parse_number

    result = run_concolic(target=parse_number, initial_args={"s": "1"})

    assert result.success
    zero_arm_line = _find_return_line(parse_number, "zero")
    assert zero_arm_line in result.executed_lines, (
        f"line {zero_arm_line} not in {sorted(result.executed_lines)} — "
        "ConcolicStr.__int__ may not be routing symbolically"
    )


def test_str_drives_alternate_arm():
    """
    Given a target whose 'zero' arm requires str(x) == "0"
    When run_concolic starts from a nonzero seed integer
    Then the engine synthesizes x = 0
      And the str-gated alternate arm line is in executed_lines
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.builtins.str_format import format_number

    result = run_concolic(target=format_number, initial_args={"x": 5})

    assert result.success
    zero_arm_line = _find_return_line(format_number, "zero")
    assert zero_arm_line in result.executed_lines, (
        f"line {zero_arm_line} not in {sorted(result.executed_lines)} — "
        "ConcolicInt.__str__ may not be routing symbolically"
    )


def test_bool_drives_alternate_arm():
    """
    Given a target whose 'falsy' arm requires bool(x) == False
    When run_concolic starts from a truthy seed integer
    Then the engine synthesizes x = 0
      And the bool-gated alternate arm line is in executed_lines
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.builtins.bool_coerce import truthiness

    result = run_concolic(target=truthiness, initial_args={"x": 1})

    assert result.success
    assert result.paths_explored >= 2
    falsy_arm_line = _find_return_line(truthiness, "falsy")
    assert falsy_arm_line in result.executed_lines, (
        f"line {falsy_arm_line} not in {sorted(result.executed_lines)} — "
        "ConcolicInt.__bool__ may not be registering the branch"
    )


def _find_return_line(func: Callable, literal: str) -> int:
    """Return the absolute source line of ``return "{literal}"`` inside ``func``.

    Dynamic discovery keeps the witness assertions resilient to fixture
    reformatting — a blank line inserted above the ``return`` would
    break a hardcoded line number but not this lookup.
    """
    source_lines, start = inspect.getsourcelines(func)
    for offset, line in enumerate(source_lines):
        if f'return "{literal}"' in line:
            return start + offset
    raise AssertionError(f'no `return "{literal}"` in {func.__name__}')
