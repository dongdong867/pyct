def encode_three_ways(s: str) -> int:
    first = s.encode("utf-8")
    second = s.encode(encoding="utf-8")
    third = s.encode("utf-8", errors="strict")
    return len(first + second + third)
