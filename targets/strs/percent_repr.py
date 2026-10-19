"""`%r` formatting of a tracked str: Python's text, plain, and a downgrade named `__mod__`.

Kept apart from `percent_formats` so the compare tool can leave this module out: legacy writes
`%r` as `str()`, so its run reaches `return 0`, which plain Python never reaches.
"""


def quoted(s: str):
    text = "%r" % (s,)
    if text == "'a'":
        return 1
    return 0
