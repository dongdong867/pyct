class Cmp:
    def __init__(self, v: int) -> None:
        self.v = v

    def __bool__(self) -> bool:
        return self.v != 0
