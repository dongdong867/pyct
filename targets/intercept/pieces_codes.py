def piece(s: str) -> str:
    first = s.split(",")[0]
    if ord(first) == 65:
        return "A"
    return "other"


def item(words: list[str]) -> str:
    if ord(words[0]) == 65:
        return "A"
    return "other"
