"""Case-fold equality branch target with a non-ASCII literal.

The branch ``s.lower() == "café"`` contains an é (U+00E9). The
charwise case-fold rewrite is unsound for non-ASCII letters — Python's
``str.lower()`` case-folds Unicode letters via the Unicode case
mappings, not via the engine's 26-deep ASCII-only ``str.replace_all``
chain. The optimizer must skip the rewrite on non-ASCII compared
literals so the baseline encoding still drives the solver.
"""


def matches_cafe(s: str) -> str:
    if s.lower() == "café":
        return "match"
    return "nomatch"
