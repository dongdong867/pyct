def helper(s):
    if s == "deep":
        return 1
    return 0


def target(s: str):
    found = s.startswith("q") or s.endswith("z")
    return helper(s), found


def other(s):
    if s:
        return 2
    return 3
