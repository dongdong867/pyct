"""A loop's summary as the model writes it: the answer's form the request gives, the form check of
the reply's code, and the two checks the formula runs through before it is kept.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyct.rewrite.condition import CALLS

# the functions a formula may call by name: a rewrite's, and those that gather a list's values
FORMULA_CALLS = CALLS | frozenset({"sum", "round", "sorted", "divmod"})
# the statements a formula holds at most, the ones inside its if statements counted
MOST_STATEMENTS = 10
# the function a formula is written as
SUMMARY = "summary"


def answer_form(parameters: Sequence[str], changed: Sequence[str]) -> str:
    """How the reply writes a formula for a loop with these names going in and changed."""
    entries = ", ".join(f'"{name}": ...' for name in changed)
    calls = ", ".join(sorted(FORMULA_CALLS))
    return (
        "Answer with one fenced Python code block that defines one function and nothing else:"
        f" def {SUMMARY}({', '.join(parameters)}):, which gives the values the loop leaves in"
        " its changed names from the values going in, without a loop. It holds at most"
        f" {MOST_STATEMENTS} statements, each an assignment to a name or an if statement that"
        " holds the same, and ends with a return of a dict with one entry per changed name,"
        f" keyed by the name: return {{{entries}}}. It may read its parameters, the names it"
        ' assigns, and their items, written x[i] or d["k"]; literals; comparisons; and, or,'
        f" not; arithmetic; {calls}; math.<function>; and the methods of the values whose names"
        " do not start with _, other than format and format_map. It has no import, other"
        " function, lambda, loop, comprehension, if expression or call of itself."
    )
