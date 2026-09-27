"""A sweep fixture: a class outside the swept package whose name another class shares."""


class Thing:
    def __init__(self, n: int) -> None:
        self.n = n
