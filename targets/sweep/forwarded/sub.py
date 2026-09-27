"""A sweep fixture: a module below a package that forwards to itself."""


def below(n: int) -> int:
    return n
