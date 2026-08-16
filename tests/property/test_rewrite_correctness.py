"""Property test for rewrite-correctness AC.

For each of the five rewrite classes shipped by smt-constraint-encoding-fixes
(substring let-binding, count, literal-container membership, str->int,
case-fold), generate inputs via Hypothesis and verify the engine's symbolic
execution path matches concrete CPython execution of the same input on the
same synthetic target.

Compared via executed-line set:
- concrete: coverage.py over a direct ``target(**args)`` call
- engine:   ``ExplorationResult.executed_lines`` after a single-iteration
            explore() with the Hypothesis-drawn input as the initial seed

Equal sets (restricted to the target function's source line range) mean
every branch in the target took the same arm under both executions, i.e.
the AST rewriter + constraint optimizer preserved branch semantics.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest
from coverage import Coverage
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine

# The if/return-True else return-False shape is intentional and noqa'd:
# the engine doesn't register branches on bare `return <Compare>` per
# project memory `project_concolic_tracking_gaps`, so collapsing these to
# `return cond` would silently disable the rewrite exercised by the test.


def target_substring(s: str) -> bool:
    """Substring let-binding rewrite (slice on symbolic str)."""
    if s[:3] == "abc":  # noqa: SIM103
        return True
    return False


def target_count(s: str) -> bool:
    """Count rewrite (str.count on symbolic str, literal sub)."""
    if s.count("a") == 2:  # noqa: SIM103
        return True
    return False


def target_membership(s: str) -> bool:
    """Literal-container membership rewrite."""
    if s in ("foo", "bar", "baz"):  # noqa: SIM103
        return True
    return False


def target_str_to_int(s: str) -> bool:
    """Str->int tracking (multichar symbolic str)."""
    try:
        n = int(s)
    except ValueError:
        return False
    return n > 10


def target_case_fold(s: str) -> bool:
    """Case-fold rewrite (str.lower on symbolic str)."""
    if s.lower() == "abc":  # noqa: SIM103
        return True
    return False


_PRINTABLE_ASCII = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=0,
    max_size=8,
)
_INT_LIKE = st.one_of(
    st.text(alphabet="0123456789", min_size=1, max_size=4),
    _PRINTABLE_ASCII,
)


def _target_line_range(target: Callable) -> frozenset[int]:
    unwrapped = inspect.unwrap(target)
    source_lines, start = inspect.getsourcelines(unwrapped)
    return frozenset(range(start, start + len(source_lines)))


def _engine_executed_lines(target: Callable, args: dict[str, Any]) -> frozenset[int]:
    """Run engine with ``args`` as the sole seed; return lines the seed iteration hit.

    The engine ignores ``max_iterations`` during seed phase, so ``executed_lines``
    accumulates a stray solver-driven iteration after the seed runs. The seed's
    own line set is captured by ``inputs_generated[0].new_lines`` — that's what
    we compare against concrete execution to test the rewrite-correctness property.
    """
    config = ExecutionConfig(max_iterations=1, timeout_seconds=10.0)
    engine = Engine(config)
    result = engine.explore(target, args, seed_inputs=[])
    if not result.inputs_generated:
        return frozenset()
    return result.inputs_generated[0].new_lines


def _concrete_executed_lines(target: Callable, args: dict[str, Any]) -> frozenset[int]:
    """Run target under coverage.py without engine instrumentation."""
    target_file = inspect.getfile(inspect.unwrap(target))
    cov = Coverage(data_file=None, include=[target_file])
    cov.start()
    try:
        target(**args)
    except Exception:
        pass
    finally:
        cov.stop()
    return frozenset(cov.get_data().lines(target_file) or [])


def _assert_paths_match(target: Callable, args: dict[str, Any]) -> None:
    func_range = _target_line_range(target)
    engine_lines = _engine_executed_lines(target, args) & func_range
    concrete_lines = _concrete_executed_lines(target, args) & func_range
    assert engine_lines == concrete_lines, (
        f"rewrite-correctness divergence for {target.__name__}({args!r}): "
        f"engine={sorted(engine_lines)} vs concrete={sorted(concrete_lines)}"
    )


_PROPERTY_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=(
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ),
)


@pytest.mark.slow
@_PROPERTY_SETTINGS
@given(s=_PRINTABLE_ASCII)
def test_substring_rewrite_preserves_branches(s: str) -> None:
    _assert_paths_match(target_substring, {"s": s})


@pytest.mark.slow
@_PROPERTY_SETTINGS
@given(s=_PRINTABLE_ASCII)
def test_count_rewrite_preserves_branches(s: str) -> None:
    _assert_paths_match(target_count, {"s": s})


@pytest.mark.slow
@_PROPERTY_SETTINGS
@given(s=_PRINTABLE_ASCII)
def test_membership_rewrite_preserves_branches(s: str) -> None:
    _assert_paths_match(target_membership, {"s": s})


@pytest.mark.slow
@_PROPERTY_SETTINGS
@given(s=_INT_LIKE)
def test_str_to_int_rewrite_preserves_branches(s: str) -> None:
    _assert_paths_match(target_str_to_int, {"s": s})


@pytest.mark.slow
@_PROPERTY_SETTINGS
@given(s=_PRINTABLE_ASCII)
def test_case_fold_rewrite_preserves_branches(s: str) -> None:
    _assert_paths_match(target_case_fold, {"s": s})
