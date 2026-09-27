"""A sweep fixture: a module with a public function."""


def last(n: int) -> int:
    if n > 0:
        return n
    return 0
