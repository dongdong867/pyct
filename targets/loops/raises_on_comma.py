def no_commas(s: str) -> str:
    for c in s:
        if c == ",":
            raise ValueError("a comma")
    return "clean"
