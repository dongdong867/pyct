"""Substring slice with concrete start and symbolic end.

The slice expression ``s[5:n]`` has a concrete literal start (5) and a
symbolic end (``n``). This fixture exercises the substr SMT emission path
that the let-binding rewrite targets — without the rewrite, the start
expression duplicates inside the substr length term.
"""


def slice_with_symbolic_end(s: str, n: int) -> str:
    if s[5:n] == "abc":
        return "match"
    return "nomatch"
