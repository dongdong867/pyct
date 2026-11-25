"""A condition that records no fork and whose value has no source pyct finds, for the
guess-inputs-when-stuck story."""


class Box:
    def __init__(self, x: int) -> None:
        self.size = bin(x).count("1")


def boxed(x: int) -> str:
    box = Box(x)
    if box.size == 7:
        return "seven"
    return "other"
