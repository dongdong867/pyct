"""Tiny target with three distinct branches — used by run_concolic_llm tests.

Each branch covers a unique body line, so seed inputs that exercise
different branches produce distinguishable coverage.
"""


def classify(x: int, y: int) -> int:
    if x > 0:
        return 1
    if y > 0:
        return 2
    return 0
