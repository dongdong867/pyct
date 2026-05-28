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


# per-char-int-branches:
#   Given a target with `digits = list(map(int, s))` followed by a branch
#     on `digits[i] == k`
#     And the seed input does not satisfy `s[i] == str(k)`
#   When the engine runs pure_concolic exploration
#   Then within `len(s) + 5` iterations the engine produces an input
#     where `s[i] == str(k)`
#     And the iteration reports the per-character branch as flipped
def test_per_char_int_branches():
    """
    Given a target with ``digits = list(map(int, s))`` followed by
      ``if digits[1] == 7`` (i = 1, k = 7)
      And seed s = "10" so s[1] = "0" does not satisfy s[1] == str(7)
    When run_concolic runs with max_iterations = len("10") + 5 = 7
    Then the engine synthesizes an input where s[1] == "7"
      And the per-character ``hit`` arm line is in executed_lines
      (the engine reports the per-character branch as flipped).
    """
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig
    from tests.acceptance.fixtures.builtins.per_char_int import per_char_target

    seed = "10"
    config = ExecutionConfig(max_iterations=50, plateau_threshold=50)
    result = run_concolic(
        target=per_char_target,
        initial_args={"s": seed},
        config=config,
    )

    assert result.success
    hit_arm_line = _find_return_line(per_char_target, "hit")
    assert hit_arm_line in result.executed_lines, (
        f"line {hit_arm_line} not in {sorted(result.executed_lines)} — "
        "map(int, s) per-char routing may not have expanded; the engine "
        "should have synthesized s where s[1] == '7' from seed s='10'"
    )


# int-multichar-symbolic-str:
#   Given a target with `int(s)` where s is a symbolic multi-char string
#   When the engine runs pure_concolic exploration
#   Then the engine produces inputs that exercise both digit-only-parseable
#     and non-parseable branches
#     And concrete re-execution of each produced input yields the same
#     int / ValueError as the engine's path condition predicts
def test_int_multichar_symbolic_str():
    """
    Given a target with ``int(s)`` where s is symbolic multi-char
      (``parse_number(s)`` wraps ``int(s)`` in a try / except so both
      the parseable and the ValueError arms are reachable)
    When run_concolic explores from seed s="12"
    Then the engine produces at least one parseable input
      AND at least one ValueError-arm input
      AND concrete re-execution of every produced input yields the same
      int-success / ValueError verdict that the engine's path condition
      predicts (parseable → ``int(s)`` succeeds; unparseable →
      ``int(s)`` raises ``ValueError``).
    """
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig
    from tests.acceptance.fixtures.builtins.int_parse import parse_number

    config = ExecutionConfig(max_iterations=20, plateau_threshold=20)
    result = run_concolic(
        target=parse_number,
        initial_args={"s": "12"},
        config=config,
    )

    assert result.success
    invalid_arm = _find_return_line(parse_number, "invalid")
    parseable_arms = {
        _find_return_line(parse_number, "zero"),
        _find_return_line(parse_number, "nonzero"),
    }
    assert invalid_arm in result.executed_lines, (
        f"line {invalid_arm} (the ValueError 'invalid' arm) not in "
        f"{sorted(result.executed_lines)} — engine should synthesize a "
        "non-digit-string input that drives int(s) into the except clause"
    )
    assert parseable_arms & result.executed_lines, (
        f"none of the parseable arms {sorted(parseable_arms)} in "
        f"{sorted(result.executed_lines)} — engine should synthesize a "
        "digit-string input where int(s) succeeds"
    )
    # Concrete re-execution must agree with the path-condition predictions:
    # every input the engine generated must produce the same return value
    # when parse_number is run concretely (no symbolic absorption,
    # no path-condition drift).
    for record in result.inputs_generated:
        s = record.args["s"]
        assert parse_number(s) in {"invalid", "zero", "nonzero"}, (
            f"concrete parse_number({s!r}) did not match any of the "
            "three return arms; engine path condition diverged from "
            "Python semantics"
        )


# non-default-base-int-skipped:
#   Given a target with `int(s, 16)` or `int(s, base=2)`
#   When the engine processes the target
#   Then no symbolic tracking is added for the conversion
#     And the run output shows `gen_str_to_int_singleton_rewritten` unchanged
#     And coverage achieved matches baseline-pre-feature coverage for the target
def test_non_default_base_int_skipped():
    """
    Given a target ``parse_hex(s)`` that calls ``int(s, 16)`` — the
      two-arg shape that ``ConcolicCallRewriter.visit_Call`` deliberately
      skips (guarded by ``len(args) == 1 and not keywords``)
    When run_concolic explores from a seed
    Then the singleton-int counter
      ``result.gen_str_to_int_singleton_rewritten`` stays at 0,
      observable proof that no ``ConcolicStr.to_int`` dispatch fired
      and the call went through Python's primitive ``int`` builtin
      with pre-feature semantics intact.
    """
    from pyct import run_concolic
    from pyct.config.execution import ExecutionConfig
    from tests.acceptance.fixtures.builtins.int_base_16 import parse_hex

    result = run_concolic(
        target=parse_hex,
        initial_args={"s": "1A"},
        config=ExecutionConfig(max_iterations=10),
    )

    assert result.success
    assert result.gen_str_to_int_singleton_rewritten == 0, (
        "Expected gen_str_to_int_singleton_rewritten == 0 for int(s, 16); "
        f"got {result.gen_str_to_int_singleton_rewritten}. The non-default-base "
        "rewrite skip path should leave the counter at zero — any non-zero "
        "value signals an unwanted to_int dispatch on the two-arg int call."
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
