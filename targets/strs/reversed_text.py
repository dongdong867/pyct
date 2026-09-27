def mirror(s: str) -> str:
    if s[::-1] == "abc":
        return "mirrored"
    return "other"
