def never_part(s: str) -> str:
    # a text holding "q" is never part of "abc"
    if s + "q" in "abc":
        return "part"
    return "not part"
