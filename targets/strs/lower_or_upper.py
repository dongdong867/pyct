def case(s: str) -> str:
    if s.islower():
        return "lower"
    if s.isupper():
        return "upper"
    return "neither"
