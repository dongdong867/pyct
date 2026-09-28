CHARS = ()


def h(s: str) -> str:
    if (
        s).strip(*CHARS) in "abc":
        return "listed"
    return "other"
