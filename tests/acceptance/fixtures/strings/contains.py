"""String contains target — spreads branches across distinct lines.

The ``in`` operator over ``ConcolicStr`` does register a constraint
(Python's ``PySequence_Contains`` coerces the result via ``PyObject_IsTrue``,
which fires ``ConcolicBool.__bool__``). The problem with a one-line
``return "://" in url`` is that full line coverage is reached in a single
iteration, so the engine terminates on ``full_coverage`` before the solver
ever processes the unexplored branch. Splitting the outcomes into two
return lines forces the engine to keep exploring until both paths are hit.
"""


def has_protocol(url: str) -> str:
    if "://" in url:
        return "with_protocol"
    return "plain"
