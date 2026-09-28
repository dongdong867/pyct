from targets.strs import rebound_separator

# another module rebinds the name its own module binds only to a str literal
rebound_separator.SEP = b"-"


def call(s):
    return rebound_separator.join_by_sep(s)
