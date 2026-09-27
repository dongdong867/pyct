def mod_empty(s: str) -> str:
    t = s % ()
    if t == "abc":
        return "matched"
    return "other"


def format_empty(s: str) -> str:
    t = s.format()
    if t == "abc":
        return "matched"
    return "other"


def mod_then_itself(s: str) -> str:
    t = s % ()
    if s == "abc":
        return "matched"
    return t
