"""A sweep fixture: classes, their constructors, and the methods their own bodies define."""


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner

    def total(self, discount: int) -> int:
        return discount

    @staticmethod
    def rate(n: int) -> int:
        return n

    @classmethod
    def empty(cls):
        return cls("")

    @property
    def size(self) -> int:
        return len(self.owner)

    def _log(self) -> None:
        return None


class Parser:
    def parse(self, text: str) -> str:
        return text


class Special(Cart):
    pass
