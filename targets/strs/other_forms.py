def other(s: str, k: int) -> list[str]:
    every_other = s[::2]
    twice = s.replace("a", "b", 2)
    stepped = s[::k]
    counted = s.replace("a", "b", k)
    return [every_other, twice, stepped, counted]
