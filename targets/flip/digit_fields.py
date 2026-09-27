def _number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    return None


def fields(a: str, b: str, c: str) -> str:
    if _number(a) is None:
        return "a"
    if _number(b) is None:
        return "b"
    if _number(c) is None:
        return "c"
    return "numbers"
