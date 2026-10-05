def wrapped(s, n):
    parts = s.split(",")
    if parts[n % len(parts)] == "z":
        return 1
    return 0


def at_a_tracked_index(s, n):
    parts = s.split(",")
    if 0 <= n < len(parts) and parts[n] == "z":
        return 1
    return 0


def from_the_end(s, n):
    parts = s.split(",")
    if 0 < n <= len(parts) and parts[-n] == "z":
        return 1
    return 0


def counted_back(s, n):
    parts = s.split(",")
    if 0 < n <= len(parts) and parts[len(parts) - n] == "z":
        return 1
    return 0


def cut_at_a_tracked_bound(s, n):
    rest = s.split(",")[n:]
    if rest and rest[0] == "z":
        return 1
    return 0


def searched_from(s, n):
    parts = s.split(",")
    if "z" in parts[1:] and parts.index("z", n) == 2:
        return 1
    return 0
