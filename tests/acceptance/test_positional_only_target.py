"""End-to-end: concolic exploration must reach the body of a target
with positional-only parameters.

Before the fix, ``run_concolic`` invoked targets as
``target(**concolic_args)``, which raises ``TypeError`` when the target
has positional-only parameters (PEP 570, ``/`` separator). The
``@validator`` decorator in ``python-validators`` swallowed that into a
``ValidationError`` return value, so exploration appeared to succeed
but executed zero body lines — Validate URL sat at 0% across every
runner in the realworld benchmark.
"""

from __future__ import annotations

import inspect


def test_run_concolic_reaches_body_of_validators_url():
    """
    Given ``validators.url`` — a target with ``value: str, /`` positional-only
    When run_concolic is invoked with the standard benchmark initial_args
    Then executed_lines contains at least one line from the ``url`` body
      (not merely the ``@validator`` decorator frame).
    """
    import validators

    from pyct import run_concolic

    result = run_concolic(
        target=validators.url,
        initial_args={"value": "https://example.com/"},
    )

    assert result.success
    body_lines = _body_statement_lines(validators.url)
    hit_body = body_lines & result.executed_lines
    assert hit_body, (
        f"no body lines hit — executed_lines={sorted(result.executed_lines)}, "
        f"body_lines={sorted(body_lines)}. The @validator wrapper likely "
        "caught a binding error before the body ran."
    )


def _body_statement_lines(func) -> frozenset[int]:
    """Return the set of executable source lines inside ``func``'s body.

    Uses coverage.py's static analysis intersected with the function's
    source range; strips the ``def`` header itself so the assertion
    measures real body coverage.
    """
    from coverage import Coverage

    unwrapped = inspect.unwrap(func)
    target_file = inspect.getfile(unwrapped)
    src, start = inspect.getsourcelines(unwrapped)
    func_range = set(range(start, start + len(src)))
    cov = Coverage(data_file=None, include=[target_file])
    stmts = set(cov.analysis(target_file)[1]) & func_range
    stmts.discard(start)  # def header
    return frozenset(stmts)
