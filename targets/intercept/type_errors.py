def in_text(n: int) -> str:
    if n in "abc":
        return "in"
    return "not in"


def in_set(items: list[int]) -> str:
    if items in {1, 2}:
        return "in"
    return "not in"
