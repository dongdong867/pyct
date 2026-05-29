"""Multi-class rewrite fixture for telemetry visibility verification.

Exercises multiple rewrite classes in a single target so a single engine
run produces non-zero counts across firing + skip counters. The branches
are layered so the solver must navigate each, exposing:

  * ``text.lower() == "abc"`` — case-fold rewrite firing
  * ``text.count("xy") == 1`` — count rewrite firing (literal sub)
  * ``text.count(marker) == 2`` — count rewrite skip (symbolic sub)
"""


def multi_rewrite(text: str, marker: str) -> str:
    if text.lower() == "abc":
        return "lower"
    if text.count("xy") == 1:
        return "count"
    if text.count(marker) == 2:
        return "symbolic"
    return "other"
