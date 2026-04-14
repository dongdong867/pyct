"""String equality target — exact match branches using CVC5 string theory."""


def check_keyword(word: str) -> int:
    if word == "admin":
        return 1
    if word == "user":
        return 2
    return 0
