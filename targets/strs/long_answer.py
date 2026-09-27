def tail_is_z(s: str) -> str:
    if s[70000:] == "z":
        return "far"
    return "near"


def past_a_million(s: str) -> str:
    if len(s) > 1_000_000:
        return "huge"
    return "fits"


def either_end(s: str) -> str:
    if s.startswith("a"):
        return "starts"
    if s.endswith("z"):
        return "ends"
    return "neither"
