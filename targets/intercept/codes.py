def codes(c: str, n: int) -> str:
    if ord(c) == 65:
        return "A"
    if chr(n) == "z":
        return "z"
    return "neither"


def code_of(c: str) -> int:
    return ord(c)


def character_of(n: int) -> str:
    return chr(n)
