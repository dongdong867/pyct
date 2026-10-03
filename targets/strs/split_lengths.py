def counted(s):
    parts = s.split(",")
    if len(parts) != 4:
        return "not four"
    return "four"


def second_empty(s):
    parts = s.split("|")
    if len(parts) != 3:
        return "not three"
    if parts[1] == "":
        return "second empty"
    return "second full"


def searched(s):
    if "b" in s.split(","):
        return "found"
    return "other"


def from_the_end(s):
    parts = s.split(",")
    if parts[-1] == "z":
        return "z"
    return "other"


def every_form(s):
    found = []
    if len(s.split()) == 3:
        found.append("words")
    if len(s.split(",", 1)) == 2:
        found.append("limited")
    if len(s.rsplit(",", 1)) == 2:
        found.append("from the right")
    if len(s.splitlines()) == 3:
        found.append("lines")
    if len(s.split(",", 1)) > 2:
        found.append("never")
    return found


def appended(s):
    parts = s.split(",")
    parts.append("z")
    if len(parts) == 3:
        return "three"
    return "other"


def first_two_joined(v):
    if ".".join(v.split(".")[:2]) == "3.12":
        if v.endswith(".1"):
            return "patch one"
        return "minor"
    return "other"


def past_the_pieces(s):
    parts = s.split(",")
    if parts[1] == "b":
        return "b"
    return "other"


def by_a_tracked_separator(s, t):
    parts = s.split(t)
    if len(parts) == 2:
        return "two"
    return "other"


def by_an_empty_separator(s):
    return len(s.split(""))


def arithmetic(s):
    parts = s.split(",")
    if len(parts) - 1 > 3:
        if parts[0] == "x":
            return 1
    if len(parts) * 2 == 8:
        pass
    if 3 < len(parts):
        pass
    return 0


def last_line(s):
    lines = s.splitlines()
    if lines[-1] == "end":
        return 1
    return 0


def beside_a_tracked_value(s, n):
    lines = s.splitlines()
    if n < 30:
        if len(lines) > n:
            if lines[0] == "end":
                return 2
    return 1


def walked_after(s):
    for i, p in enumerate(s.splitlines()):
        if i > 0 and p == "end":
            return 1
    return 0
