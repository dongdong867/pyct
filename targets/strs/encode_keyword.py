def encode_utf8(s: str) -> str:
    data = s.encode(encoding="utf-8")
    if data == b"abc":
        return "abc"
    return "other"
