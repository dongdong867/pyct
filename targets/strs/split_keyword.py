def split_on_comma(s: str) -> str:
    parts = s.split(sep=",")
    if parts == ["a", "b"]:
        return "two"
    return "other"
