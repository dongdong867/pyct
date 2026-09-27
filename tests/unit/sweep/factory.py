"""Code ``edges`` holds that this module holds under no name, and a base with a constructor."""


def make_class() -> type:
    class Built:
        def __init__(self, n: int) -> None:
            self.n = n

    return Built


class Base:
    def __init__(self, n: int) -> None:
        self.n = n
