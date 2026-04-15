"""Branches driven by len() — regression witness for builtins.len monkey-patch.

The ``long`` arm is only reachable when ``len(s)`` returns a ConcolicInt
carrying the ``str.len`` expression. Without the environment_preparer
monkey-patch ``builtins.len = lambda x: x.__len__()``, Python's
``PyObject_Size`` coerces the result to a raw int and strips the symbolic
expression, leaving the engine unable to synthesize a 6+ character input.
"""


def check_length(s: str) -> str:
    if len(s) == 0:
        return "empty"
    if len(s) > 5:
        return "long"
    return "short"
