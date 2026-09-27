class Forest:
    """A union-find chain whose `find` recurses once per link, as plain code writes it."""

    def __init__(self, size: int) -> None:
        self.parent = [max(link - 1, 0) for link in range(size)]

    def find(self, x: int) -> int:
        if self.parent[x] == x:
            return x
        return self.find(self.parent[x])


def deep_find(x: int) -> int:
    root = Forest(700).find(699)
    if x > 3:
        return root
    return -1


def int(value: int) -> int:
    # the module's own `int`, which recurses once per step down to zero
    if value <= 0:
        return 0
    return int(value - 1)


def deep_own_int(x: int) -> int:
    if int(700) == 0 and x > 3:
        return 1
    return 0


class Link:
    """A chain whose reflected `+` recurses once per link, with a float literal on the left."""

    def __init__(self, rest: "Link | None") -> None:
        self.rest = rest

    def __radd__(self, other: float) -> float:
        if self.rest is None:
            return other
        return 0.5 + self.rest


def deep_radd(x: int) -> int:
    chain = None
    for _ in range(700):
        chain = Link(chain)
    if 0.5 + chain == 0.5 and x > 3:
        return 1
    return 0

