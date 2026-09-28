from targets.strs import rebound_separator


def check(sep, a):
    # another module rebinds the name its own module binds only to a str literal, to a tracked str
    rebound_separator.SEP = sep
    if rebound_separator.join_by_sep(a) == "q-b":
        if a.startswith("z"):
            return "z"
        return "q"
    return "other"
