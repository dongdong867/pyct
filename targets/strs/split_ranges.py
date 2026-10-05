def truth(s):
    parts = s.split(",")
    if parts:
        if parts[0] == "end":
            return 2
        return 1
    return 0


def counted_again(s):
    parts = s.split(",")
    if len(parts) == 4:
        if len(parts) > 2:
            if parts[3] == "end":
                return 2
            return 1
    return 0


def joined_after_the_count(s):
    parts = s.split(",")
    if len(parts) == 3:
        if "-".join(parts) == "a-b-end":
            return 2
        return 1
    return 0


def limited_from_the_right(s):
    parts = s.rsplit(",", 2)
    if len(parts) <= 3:
        if parts[-1] == "end":
            return 2
        return 1
    return 0


def appended_display(s):
    parts = s.split(",") + ["z"]
    if len(parts) > 1:
        return 1
    return 0


def words(s):
    parts = s.split()
    if parts:
        return 1
    return 0


def lines(s):
    parts = s.splitlines()
    if parts:
        return 1
    return 0


def against_a_tracked_count(s, n):
    parts = s.split(",")
    if len(parts) == n:
        if len(parts) > 2:
            return 2
        return 1
    return 0


def walked(s):
    parts = s.split(",")
    for p in parts:
        pass
    if parts:
        pass
    if len(parts) > 0:
        if "b" in parts:
            return 1
    return 0


def past_a_limit(s):
    parts = s.split(",", 1)
    if parts[2] == "x":
        return 1
    return 0
