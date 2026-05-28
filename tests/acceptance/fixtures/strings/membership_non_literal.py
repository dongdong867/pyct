"""Non-literal container membership target.

The rewriter must skip ``Compare(In, ...)`` whose comparator is NOT a
literal Set/Tuple/List/Dict AST node. Here the container is a
module-level ``tuple`` bound to a Name — the AST sees ``ast.Name``,
not ``ast.Tuple``, so the rewrite path falls through and the
non-literal-skip counter increments.

Anchors the ``non-literal-container-skipped`` AC: the engine treats
this branch with pre-feature semantics (Python's untracked
``__contains__``) so the engine's emitted constraints are identical
to what they would be without the membership rewrite feature.
"""

_KEYWORDS = ("alpha", "beta", "gamma")


def has_keyword(x: str) -> str:
    if x in _KEYWORDS:
        return "match"
    return "nomatch"
