def check(s: str) -> str:
    size = 0
    size += 1
    # the check sits on line 5, indented four spaces
    if len(s) > 3:
        return "long"
    return "short"
