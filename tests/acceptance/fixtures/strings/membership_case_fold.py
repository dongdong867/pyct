"""Composition fixture: case-insensitive membership against a literal container.

Exercises the combined behavior of the literal-container membership AST
rewrite (Task 3) and the case-fold equality rewrite (Task 6). The
membership rewriter expands ``x.lower() in {"yes", "no"}`` into
``x.lower() == "yes" or x.lower() == "no"``, then each ``==`` triggers
the case-fold equality rewrite under the constraint optimizer so the
solver can drive each disjunct charwise.
"""


def in_lower_set(x: str) -> str:
    if x.lower() in {"yes", "no"}:
        return "match"
    return "nomatch"
