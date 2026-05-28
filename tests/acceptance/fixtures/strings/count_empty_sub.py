"""Empty-substring count target.

Python's ``str.count("")`` returns ``len(s) + 1`` — every position
between (and including) the endpoints counts as one empty-string
match. The branch ``s.count("") == 3`` therefore selects strings of
length exactly 2. The constraint-optimizer's count-rewrite must
preserve this semantics: the existing ``replace_all+div`` ITE form
handles empty-sub via a separate ``+ 1 + str.len`` arm, and the
rewrite must NOT clobber that arm when it substitutes the general
``str.indexof`` chain for non-empty literal subs.
"""


def matches_empty_count(s: str) -> str:
    if s.count("") == 3:
        return "match"
    return "nomatch"
